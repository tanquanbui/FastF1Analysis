"""FastF1 wrapper — load session data and normalise into plain DataFrames.

FastF1 caches session payloads on disk (`FASTF1_CACHE_DIR`). On Lambda we point
this at `/tmp` so the cache is warm within a single execution but discarded
between invocations.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import fastf1
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = os.environ.get("FASTF1_CACHE_DIR", "/tmp/fastf1_cache")
SESSION_TYPES = {
    "R": "Race",
    "Q": "Qualifying",
    "S": "Sprint",
    "SQ": "Sprint Qualifying",
    "SS": "Sprint Shootout",
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
}

_cache_enabled = False


def _ensure_cache() -> None:
    """Configure FastF1's on-disk cache. Idempotent."""
    global _cache_enabled
    if _cache_enabled:
        return
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)
    _cache_enabled = True
    logger.info("FastF1 cache enabled at %s", CACHE_DIR)


def get_session_laps(year: int, round_number: int, session_type: str) -> pd.DataFrame:
    """Load lap-level data (times, sectors, tyres, position, stint).

    Returns an empty DataFrame if the session has not yet run.
    """
    _ensure_cache()
    if session_type not in SESSION_TYPES:
        raise ValueError(f"unknown session_type {session_type!r}; expected one of {list(SESSION_TYPES)}")

    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=False, weather=True, messages=False)

    laps = session.laps
    if laps.empty:
        logger.warning("no laps for %s-%s %s", year, round_number, session_type)
        return pd.DataFrame()

    columns = [
        "Driver",
        "DriverNumber",
        "Team",
        "LapTime",
        "Sector1Time",
        "Sector2Time",
        "Sector3Time",
        "Compound",
        "TyreLife",
        "LapNumber",
        "Position",
        "Stint",
        "IsPersonalBest",
        "TrackStatus",
        "PitInTime",
        "PitOutTime",
        "SpeedI1",
        "SpeedI2",
        "SpeedFL",
        "SpeedST",
    ]
    available = [c for c in columns if c in laps.columns]
    return laps[available].copy()


def get_session_results(year: int, round_number: int, session_type: str = "R") -> pd.DataFrame:
    """Finishing classification for the given session."""
    _ensure_cache()
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=False, weather=False, messages=False)

    results = session.results
    if results is None or results.empty:
        return pd.DataFrame()

    keep = [
        "DriverNumber",
        "Abbreviation",
        "TeamName",
        "TeamId",
        "Position",
        "GridPosition",
        "Q1",
        "Q2",
        "Q3",
        "Time",
        "Status",
        "Points",
        "ClassifiedPosition",
    ]
    available = [c for c in keep if c in results.columns]
    return results[available].copy()


def get_speed_trap_data(year: int, round_number: int) -> pd.DataFrame:
    """Max speed-trap reading per driver across the race.

    A proxy for straight-line performance — used for the
    ``straight_line_speed`` fingerprint dimension.
    """
    laps = get_session_laps(year, round_number, "R")
    if laps.empty or "SpeedST" not in laps.columns:
        return pd.DataFrame(columns=["Driver", "Team", "MaxSpeedST", "MaxSpeedFL"])

    grouped = laps.groupby(["Driver", "Team"], as_index=False).agg(
        MaxSpeedST=("SpeedST", "max"),
        MaxSpeedFL=("SpeedFL", "max") if "SpeedFL" in laps.columns else ("SpeedST", "max"),
    )
    return grouped


def get_weather_summary(year: int, round_number: int, session_type: str = "R") -> dict:
    """Aggregate weather samples for the session — used to flag wet conditions."""
    _ensure_cache()
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=False, weather=True, messages=False)

    weather = session.weather_data
    if weather is None or weather.empty:
        return {"is_wet": False, "samples": 0}

    rainfall_pct = float((weather["Rainfall"] == True).mean()) if "Rainfall" in weather.columns else 0.0
    return {
        "is_wet": rainfall_pct > 0.1,
        "rainfall_fraction": rainfall_pct,
        "avg_air_temp_c": float(weather["AirTemp"].mean()) if "AirTemp" in weather.columns else None,
        "avg_track_temp_c": float(weather["TrackTemp"].mean()) if "TrackTemp" in weather.columns else None,
        "avg_humidity_pct": float(weather["Humidity"].mean()) if "Humidity" in weather.columns else None,
        "samples": int(len(weather)),
    }
