"""AI race simulator.

Claude reads a race context (circuit, grid, pace, tyres, weather) plus an
optional "what if" scenario and simulates the Grand Prix lap by lap: strategy
calls, pit stops, safety cars, overtakes, retirements and the final result.

    from simulator import RaceSimulator, build_context

    ctx = build_context(2024, 5, source="auto")
    session = RaceSimulator().start(ctx)
    result = session.run("Rain arrives on lap 30")
    follow_up = session.what_if("What if NOR had pitted under the safety car?")
"""
from __future__ import annotations

from .context import CircuitInfo, DriverEntry, RaceContext, build_context
from .engine import (
    DEFAULT_MODEL,
    MonteCarloSummary,
    RaceSimulator,
    SimulationError,
    SimulationResult,
    SimulationSession,
)
from .schema import RaceSimulation

__all__ = [
    "DEFAULT_MODEL",
    "CircuitInfo",
    "DriverEntry",
    "MonteCarloSummary",
    "RaceContext",
    "RaceSimulation",
    "RaceSimulator",
    "SimulationError",
    "SimulationResult",
    "SimulationSession",
    "build_context",
]
