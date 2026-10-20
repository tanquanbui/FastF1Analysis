"""Offline demo simulation - no API call, no AI.

A deliberately simple deterministic pace model that produces a structurally
valid ``RaceSimulation``. It lets the dashboard and tests run without an
Anthropic API key; the output is clearly labelled as a demo.
"""
from __future__ import annotations

import random

from .context import DriverEntry, RaceContext
from .schema import (
    ClassifiedDriver,
    DriverStrategy,
    LapOrder,
    PaceRead,
    PitStop,
    RaceEvent,
    RaceSimulation,
    Stint,
    StrategyInsight,
)

# Fallback field when the context carries no entry list (2024 grid order).
DEFAULT_FIELD = [
    ("VER", "RBR"), ("NOR", "MCL"), ("LEC", "FER"), ("PIA", "MCL"), ("SAI", "FER"), ("RUS", "MER"),
    ("HAM", "MER"), ("PER", "RBR"), ("ALO", "AST"), ("HUL", "HAA"), ("TSU", "RB"), ("STR", "AST"),
    ("GAS", "ALP"), ("OCO", "ALP"), ("ALB", "WIL"), ("RIC", "RB"), ("MAG", "HAA"), ("BOT", "SAU"),
    ("ZHO", "SAU"), ("SAR", "WIL"),
]


def demo_simulation(ctx: RaceContext, scenario: str | None = None, seed: int = 7) -> RaceSimulation:
    rng = random.Random(seed)
    laps = ctx.circuit.laps
    drivers = ctx.drivers or [DriverEntry(code=c, team=t, grid=i + 1) for i, (c, t) in enumerate(DEFAULT_FIELD)]
    drivers = sorted(drivers, key=lambda d: d.grid or 99)
    grid = {d.code: (d.grid or i + 1) for i, d in enumerate(drivers)}
    team = {d.code: d.team for d in drivers}

    base = 90.0
    pace = {
        d.code: base + (d.quali_gap_s if d.quali_gap_s is not None else 0.06 * grid[d.code]) + rng.uniform(-0.15, 0.15)
        for d in drivers
    }
    pit_lap = {d.code: max(2, min(laps - 2, int(laps * 0.42) + rng.randint(-4, 4))) for d in drivers}
    dnf_driver = drivers[-3].code if len(drivers) > 5 else None
    dnf_lap = int(laps * 0.6)

    total = {d.code: 0.3 * grid[d.code] for d in drivers}  # start spacing
    lap_chart: list[LapOrder] = []
    fastest = (None, 1e9)
    running = [d.code for d in drivers]
    for lap in range(1, laps + 1):
        if dnf_driver and lap == dnf_lap + 1 and dnf_driver in running:
            running.remove(dnf_driver)
        for code in running:
            stint_age = lap if lap <= pit_lap[code] else lap - pit_lap[code]
            compound_offset = 0.0 if lap <= pit_lap[code] else 0.25
            t = pace[code] + compound_offset + 0.04 * stint_age - 0.06 * lap + rng.uniform(-0.2, 0.2)
            if lap == pit_lap[code]:
                t += ctx.circuit.pit_loss_s
            elif t < fastest[1]:
                fastest = (code, t)
            total[code] += t
        order = sorted(running, key=lambda c: total[c])
        lap_chart.append(LapOrder(lap=lap, order=order))

    final = lap_chart[-1].order
    winner_time = total[final[0]]
    classification: list[ClassifiedDriver] = []
    for pos, code in enumerate(final, start=1):
        classification.append(
            ClassifiedDriver(
                position=pos, driver=code, team=team[code], grid=grid[code], status="Finished",
                gap="Winner" if pos == 1 else f"+{total[code] - winner_time:.3f}s",
                laps_completed=laps, fastest_lap=code == fastest[0],
            )
        )
    if dnf_driver:
        classification.append(
            ClassifiedDriver(
                position=len(final) + 1, driver=dnf_driver, team=team[dnf_driver], grid=grid[dnf_driver],
                status="DNF - power unit", gap=f"DNF L{dnf_lap}", laps_completed=dnf_lap, fastest_lap=False,
            )
        )

    strategies = []
    for d in drivers:
        end = dnf_lap if d.code == dnf_driver else laps
        if pit_lap[d.code] < end:
            stints = [
                Stint(compound="MEDIUM", start_lap=1, end_lap=pit_lap[d.code], avg_lap_s=round(pace[d.code] + 0.4, 3)),
                Stint(compound="HARD", start_lap=pit_lap[d.code] + 1, end_lap=end, avg_lap_s=round(pace[d.code] + 0.2, 3)),
            ]
            stops = [PitStop(lap=pit_lap[d.code], from_compound="MEDIUM", to_compound="HARD",
                             stationary_s=round(rng.uniform(2.2, 3.1), 1), under_neutralisation=False,
                             reason="Planned one-stop window")]
        else:
            stints = [Stint(compound="MEDIUM", start_lap=1, end_lap=end)]
            stops = []
        strategies.append(DriverStrategy(driver=d.code, planned_strategy="M-H one-stop", stints=stints, pit_stops=stops))

    best = min(pace.values())
    winner = final[0]
    return RaceSimulation(
        headline=f"[DEMO] {winner} wins the {ctx.year} {ctx.event_name}",
        weather_summary=ctx.weather or "Dry, typical conditions (demo)",
        classification=classification,
        strategies=strategies,
        events=[
            RaceEvent(lap=1, type="START", drivers=[lap_chart[0].order[0]], description="Clean start, grid order largely holds."),
            *(
                [RaceEvent(lap=dnf_lap, type="RETIREMENT", drivers=[dnf_driver], description=f"{dnf_driver} stops with a power unit issue.")]
                if dnf_driver else []
            ),
            RaceEvent(lap=laps, type="FINISH", drivers=[winner], description=f"{winner} takes the chequered flag."),
        ],
        lap_chart=lap_chart,
        pace=[
            PaceRead(driver=c, race_pace_delta_s=round(p - best, 3), tyre_deg="medium", comment="Demo pace model")
            for c, p in sorted(pace.items(), key=lambda kv: kv[1])
        ],
        insights=[
            StrategyInsight(
                title="This is a demo run",
                detail="Generated by a simple offline pace model, not by Claude. Set ANTHROPIC_API_KEY to run real AI simulations.",
            ),
            *(
                [StrategyInsight(title="Scenario not applied", detail=f"The demo model ignores scenarios ('{scenario}').")]
                if scenario else []
            ),
        ],
        narrative=(
            f"Demo simulation of the {ctx.year} {ctx.event_name}. {winner} converted pace into the win "
            f"on a one-stop medium-hard strategy over {laps} laps."
        ),
        assumptions=["Offline demo pace model; no AI involved."],
    )
