"""Command-line race simulator.

    python -m simulator races 2025
    python -m simulator run 2024 5 --scenario "Rain from lap 30"
    python -m simulator run 2024 5 --runs 5            # Monte Carlo
    python -m simulator chat 2024 5                    # interactive what-ifs
    python -m simulator context 2024 5                 # print the prompt context only (no API call)
    python -m simulator prefetch 2024                  # load + cache every 2024 weekend from FastF1
    python -m simulator prefetch 2024 --rounds 1-5

Needs ANTHROPIC_API_KEY (or an `ant auth login` profile) for anything that
simulates.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .circuits import list_calendar
from .context import RaceContext, build_context
from .engine import MonteCarloSummary, RaceSimulator, SimulationError, SimulationResult
from .store import ContextCache, History


def _context(year: int, rnd: int, source: str, refresh: bool = False) -> RaceContext:
    cache = ContextCache()
    ctx = None if refresh else cache.get(year, rnd, source)
    if ctx is None:
        ctx = build_context(year, rnd, source=source, progress=lambda m: print(f"  {m}...", file=sys.stderr))
        cache.put(ctx, source)
    return ctx


def _rounds(spec: str | None, year: int) -> list[int]:
    if spec:
        out: list[int] = []
        for part in spec.split(","):
            a, _, b = part.partition("-")
            out += list(range(int(a), int(b or a) + 1))
        return out
    return [r["round"] for r in list_calendar(year)] or list(range(1, 25))


def _print_result(result: SimulationResult) -> None:
    sim = result.simulation
    print(f"\n=== {sim.headline} ===")
    print(f"Conditions: {sim.weather_summary}\n")
    print(f"{'Pos':>3}  {'Drv':<4} {'Team':<5} {'Grid':>4}  {'Gap':<14} {'Stops':>5}  Strategy")
    strategies = {s.driver: s for s in sim.strategies}
    for c in sim.classification:
        s = strategies.get(c.driver)
        stints = "-".join(st.compound[0] for st in s.stints) if s else "?"
        flag = " *FL" if c.fastest_lap else ""
        print(
            f"{c.position:>3}  {c.driver:<4} {c.team:<5} {c.grid:>4}  {c.gap:<14} "
            f"{len(s.pit_stops) if s else 0:>5}  {stints}{flag}"
        )
    print("\nKey moments:")
    for e in sim.events:
        print(f"  L{e.lap:<3} {e.type:<18} {e.description}")
    print("\nStrategy insights:")
    for i in sim.insights:
        print(f"  - {i.title}: {i.detail}")
    print(f"\n{sim.narrative}\n")
    if result.comparison:
        c = result.comparison
        print(
            f"vs actual: winner {'correct' if c['winner_correct'] else 'wrong'}, "
            f"podium overlap {c['podium_overlap']}/3, mean position error {c['mean_abs_position_error']}"
        )
    if result.issues:
        print("Unresolved consistency issues:\n  " + "\n  ".join(result.issues))
    u = result.usage
    print(f"[tokens in {u.input_tokens} (+{u.cache_read_input_tokens} cached) / out {u.output_tokens}]")


def _print_summary(summary: MonteCarloSummary) -> None:
    print(f"\n=== Monte Carlo: {summary.runs} runs ===")
    print(f"{'Drv':<4} {'Win':>6} {'Podium':>7} {'Points':>7} {'DNF':>6} {'Avg pos':>8}")
    for d, avg in summary.average_finish.items():
        print(
            f"{d:<4} {summary.win_probability.get(d, 0):>6.0%} {summary.podium_probability.get(d, 0):>7.0%} "
            f"{summary.points_probability.get(d, 0):>7.0%} {summary.dnf_probability.get(d, 0):>6.0%} {avg:>8.2f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simulator", description="AI-driven F1 race simulator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_races = sub.add_parser("races", help="list the calendar for a season")
    p_races.add_argument("year", type=int)

    p_pre = sub.add_parser("prefetch", help="load and cache race contexts ahead of time")
    p_pre.add_argument("year", type=int)
    p_pre.add_argument("--rounds", help="e.g. 1-5 or 3,7,9 (default: whole season)")
    p_pre.add_argument("--source", choices=["fastf1", "fixtures", "model"], default="fastf1")
    p_pre.add_argument("--refresh", action="store_true", help="rebuild even if cached")

    for name in ("run", "chat", "context"):
        p = sub.add_parser(name)
        p.add_argument("year", type=int)
        p.add_argument("round", type=int)
        p.add_argument("--source", choices=["auto", "fastf1", "fixtures", "model"], default="auto")
        p.add_argument("--refresh", action="store_true", help="rebuild the race context instead of using the cache")
        if name in ("run", "chat"):
            p.add_argument("--scenario", help="what-if premise for the race, e.g. 'VER starts from the pit lane'")
            p.add_argument("--model", help="Claude model id (default claude-opus-5-5 or $SIM_MODEL)")
            p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
        if name == "run":
            p.add_argument("--runs", type=int, default=1, help="independent runs for win/podium probabilities")
            p.add_argument("--out", type=Path, help="write the full JSON result here")

    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    if args.cmd == "races":
        for r in list_calendar(args.year):
            print(f"{r['round']:>2}  {r['circuit_key']:<14} {r['event_name']} - {r['circuit']}")
        return 0

    if args.cmd == "prefetch":
        failed = 0
        for rnd in _rounds(args.rounds, args.year):
            try:
                ctx = _context(args.year, rnd, args.source, refresh=args.refresh)
                print(f"R{rnd:>2} {ctx.event_name}: {len(ctx.drivers)} drivers, {len(ctx.tables)} tables")
            except Exception as exc:  # noqa: BLE001 - keep going through the season
                failed += 1
                print(f"R{rnd:>2} failed: {exc}", file=sys.stderr)
        return 1 if failed else 0

    ctx = _context(args.year, args.round, args.source, refresh=args.refresh)
    if args.cmd == "context":
        print(ctx.to_prompt())
        return 0

    kwargs = {k: v for k, v in (("model", args.model), ("effort", args.effort)) if v}
    simulator = RaceSimulator(**kwargs)
    history = History()
    try:
        if args.cmd == "run" and args.runs > 1:
            summary = simulator.simulate_many(
                ctx, args.scenario, runs=args.runs, on_session=lambda s: history.save_session(s, args.source)
            )
            for r in summary.results:
                history.save_result(r, "ai")
            _print_summary(summary)
            payload = summary.model_dump(mode="json")
        elif args.cmd == "run":
            session = simulator.start(ctx)
            result = session.run(args.scenario)
            history.save_session(session, args.source)
            history.save_result(result, "ai")
            _print_result(result)
            payload = result.model_dump(mode="json")
        else:
            session = simulator.start(ctx)
            print(f"Simulating {ctx.year} {ctx.event_name}...")
            result = session.run(args.scenario)
            history.save_session(session, args.source)
            history.save_result(result, "ai")
            _print_result(result)
            while True:
                try:
                    question = input("\nwhat if> ").strip()
                except EOFError:
                    break
                if question.lower() in ("", "q", "quit", "exit"):
                    break
                result = session.what_if(question)
                history.save_session(session, args.source)
                history.save_result(result, "ai")
                _print_result(result)
            return 0
    except SimulationError as exc:
        print(f"Simulation failed: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.write_text(json.dumps(payload, indent=2))
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
