"""Structured output Claude returns for one simulated race.

The schema is sent to the API as a JSON-schema output format, so every response
parses straight into ``RaceSimulation``. Keep fields simple (no numeric
constraints) - ``validate.py`` does the cross-field checks.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Compound = Literal["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
EventType = Literal[
    "START", "OVERTAKE", "PIT_STOP", "UNDERCUT", "OVERCUT", "SAFETY_CAR", "VIRTUAL_SAFETY_CAR",
    "RED_FLAG", "RESTART", "RETIREMENT", "INCIDENT", "PENALTY", "WEATHER", "FASTEST_LAP",
    "TEAM_ORDERS", "STRATEGY_CALL", "FINISH",
]


class Stint(BaseModel):
    compound: Compound
    start_lap: int = Field(description="First lap of the stint (1 for the opening stint)")
    end_lap: int = Field(description="Last lap completed on this set (the in-lap, or the final lap)")
    avg_lap_s: float | None = Field(default=None, description="Representative green-flag lap time on this stint")


class PitStop(BaseModel):
    lap: int
    from_compound: Compound
    to_compound: Compound
    stationary_s: float = Field(description="Time stationary in the box, e.g. 2.4")
    under_neutralisation: bool = Field(description="True if taken under SC/VSC/red flag")
    reason: str = Field(description="Why the team called it then: undercut, cover, SC, deg cliff, weather...")


class DriverStrategy(BaseModel):
    driver: str = Field(description="Three-letter driver code")
    planned_strategy: str = Field(description="Pre-race plan, e.g. 'M-H one-stop, window L18-24'")
    stints: list[Stint]
    pit_stops: list[PitStop]


class ClassifiedDriver(BaseModel):
    position: int
    driver: str
    team: str
    grid: int
    status: str = Field(description="'Finished', '+1 Lap', or 'DNF - <cause>' / 'DSQ'")
    gap: str = Field(description="'Winner', '+4.312s', '+1 Lap', or 'DNF L34'")
    laps_completed: int
    fastest_lap: bool


class RaceEvent(BaseModel):
    lap: int
    type: EventType
    drivers: list[str] = Field(description="Driver codes involved, may be empty")
    description: str


class LapOrder(BaseModel):
    lap: int
    order: list[str] = Field(description="Running order at the end of this lap, leader first; retired drivers removed")


class PaceRead(BaseModel):
    driver: str
    race_pace_delta_s: float = Field(description="Average green-flag lap delta to the fastest driver's pace, seconds")
    tyre_deg: Literal["low", "medium", "high"]
    comment: str


class StrategyInsight(BaseModel):
    title: str
    detail: str


class RaceSimulation(BaseModel):
    headline: str = Field(description="One-line result headline")
    weather_summary: str
    classification: list[ClassifiedDriver] = Field(description="Every starter exactly once, P1 first; DNFs at the bottom")
    strategies: list[DriverStrategy] = Field(description="One entry per starter")
    events: list[RaceEvent] = Field(description="Chronological key moments")
    lap_chart: list[LapOrder] = Field(description="Running order at the end of every lap from 1 to the final lap")
    pace: list[PaceRead]
    insights: list[StrategyInsight] = Field(description="3-6 strategic takeaways a race engineer would brief")
    narrative: str = Field(description="Race report, 3-6 short paragraphs")
    assumptions: list[str] = Field(description="Assumptions you made where data was missing")
