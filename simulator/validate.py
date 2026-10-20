"""Consistency checks and derived fields for a simulated race.

Claude's output is schema-valid by construction, but schema validity doesn't
guarantee a coherent race (duplicate positions, stints with gaps, a lap chart
that skips laps). ``check`` lists problems so the engine can ask for a fix.
"""
from __future__ import annotations

from typing import Any

from .context import RaceContext
from .schema import RaceSimulation

POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}


def check(sim: RaceSimulation, ctx: RaceContext) -> list[str]:
    issues: list[str] = []
    laps = ctx.circuit.laps
    codes = [c.driver for c in sim.classification]

    if len(set(codes)) != len(codes):
        dupes = sorted({c for c in codes if codes.count(c) > 1})
        issues.append(f"classification lists drivers more than once: {', '.join(dupes)}")
    positions = sorted(c.position for c in sim.classification)
    if positions != list(range(1, len(positions) + 1)):
        issues.append("classification positions must run 1..N with no gaps or repeats")
    if ctx.drivers:
        missing = sorted(set(ctx.driver_codes) - set(codes))
        if missing:
            issues.append(f"classification is missing starters: {', '.join(missing)}")
    if sum(1 for c in sim.classification if c.fastest_lap) > 1:
        issues.append("more than one driver is marked with the fastest lap")

    strat = {s.driver: s for s in sim.strategies}
    no_strategy = sorted(set(codes) - set(strat))
    if no_strategy:
        issues.append(f"no strategy for: {', '.join(no_strategy)}")
    by_driver = {c.driver: c for c in sim.classification}
    for code, s in strat.items():
        if not s.stints:
            issues.append(f"{code}: no stints")
            continue
        if s.stints[0].start_lap != 1:
            issues.append(f"{code}: first stint must start on lap 1")
        for prev, nxt in zip(s.stints, s.stints[1:]):
            if nxt.start_lap != prev.end_lap + 1:
                issues.append(f"{code}: stints are not contiguous (L{prev.end_lap} -> L{nxt.start_lap})")
        finished_laps = by_driver[code].laps_completed if code in by_driver else laps
        if s.stints[-1].end_lap != finished_laps:
            issues.append(
                f"{code}: last stint ends L{s.stints[-1].end_lap} but laps_completed is {finished_laps}"
            )
        if len(s.pit_stops) != len(s.stints) - 1:
            issues.append(f"{code}: {len(s.stints)} stints but {len(s.pit_stops)} pit stops")

    chart_laps = [lo.lap for lo in sim.lap_chart]
    if chart_laps != list(range(1, laps + 1)):
        issues.append(f"lap_chart must contain every lap 1..{laps} exactly once, in order")
    for lo in sim.lap_chart:
        if len(set(lo.order)) != len(lo.order):
            issues.append(f"lap_chart lap {lo.lap} repeats a driver")
            break
    if sim.lap_chart:
        finishers = [c.driver for c in sim.classification if c.laps_completed >= laps]
        if sim.lap_chart[-1].order[: len(finishers)] != finishers:
            issues.append("final lap of lap_chart doesn't match the classification order of finishers")
    return issues


def points_for(sim: RaceSimulation, year: int) -> dict[str, int]:
    """Championship points. Fastest-lap bonus applied only 2019-2024."""
    pts: dict[str, int] = {}
    for c in sim.classification:
        p = POINTS.get(c.position, 0) if not c.status.upper().startswith(("DNF", "DSQ")) else 0
        if c.fastest_lap and 2019 <= year <= 2024 and c.position <= 10:
            p += 1
        pts[c.driver] = p
    return pts


def compare_to_actual(sim: RaceSimulation, actual: list[str] | None) -> dict[str, Any] | None:
    """How close the simulated order came to the real result (past races only)."""
    if not actual:
        return None
    real_pos = {code: i + 1 for i, code in enumerate(actual)}
    deltas = {
        c.driver: c.position - real_pos[c.driver] for c in sim.classification if c.driver in real_pos
    }
    if not deltas:
        return None
    sim_top3 = [c.driver for c in sim.classification[:3]]
    return {
        "actual_order": actual,
        "winner_correct": bool(sim.classification) and sim.classification[0].driver == actual[0],
        "podium_overlap": len(set(sim_top3) & set(actual[:3])),
        "mean_abs_position_error": round(sum(abs(d) for d in deltas.values()) / len(deltas), 2),
        "position_delta": deltas,
    }
