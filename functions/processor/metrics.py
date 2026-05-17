"""Race-level metric aggregations — team / sector / tyre / pit stats.

Phase 1 metrics. Fingerprint computation lives in functions/fingerprint/.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from transformers import normalise_team_code

logger = logging.getLogger(__name__)


def compute_race_flags(laps: pd.DataFrame, weather: dict[str, Any] | None) -> dict[str, Any]:
    """Compute race-level flags from lap data and weather summary."""
    flags: dict[str, Any] = {"WetRace": False, "SafetyCarLapPct": 0.0}
    if weather and weather.get("is_wet"):
        flags["WetRace"] = True
    if not laps.empty and "TrackStatus" in laps.columns:
        statuses = laps["TrackStatus"].astype(str)
        non_green = statuses.apply(lambda s: any(c in s for c in "234567"))
        if len(statuses) > 0:
            flags["SafetyCarLapPct"] = round(float(non_green.mean()), 3)
    return flags


def compute_driver_race_metrics(
    results: list[dict[str, Any]],
    qualifying: list[dict[str, Any]],
    year: int,
    round_number: int,
) -> list[dict[str, Any]]:
    """One DRIVER_METRICS record per driver per race — feeds the driver-level
    predictor. Combines the Ergast race result with the qualifying result.
    """
    from transformers import normalise_team_code  # local import to avoid cycle
    quali_by_code = {q.get("driver_code"): q for q in qualifying if q.get("driver_code")}
    items = []
    for r in results:
        code = r.get("driver_code") or r.get("driver_id", "").upper()[:3]
        team_code = normalise_team_code(r.get("constructor_id", ""))
        grid = int(r["grid"]) if r.get("grid") is not None else None
        position = r.get("position")
        finished = (r.get("status") == "Finished") or (r.get("status", "").startswith("+"))
        items.append(
            {
                "PK": f"RACE#{year}#{round_number}",
                "SK": f"DRIVER_METRICS#{code}",
                "DriverCode": code,
                "RaceKey": f"{year}#{round_number}",
                "TeamCode": team_code,
                "Grid": grid,
                "Position": position,
                "Points": r.get("points"),
                "Status": r.get("status"),
                "Finished": finished,
                "GridToFinishDelta": (grid - position) if (grid and position) else None,
                "QualifyingPosition": int(quali_by_code[code]["position"]) if code in quali_by_code else None,
                "QualifyingGapToPole": (
                    _gap_to_pole_qualifying(quali_by_code[code], qualifying)
                    if code in quali_by_code else None
                ),
            }
        )
    return items


def _gap_to_pole_qualifying(driver_q: dict[str, Any], all_q: list[dict[str, Any]]) -> float | None:
    """Compute the driver's qualifying gap-to-pole in seconds."""
    if not all_q:
        return None
    pole = all_q[0]
    own_best = _qual_best_seconds(driver_q)
    pole_best = _qual_best_seconds(pole)
    if own_best is None or pole_best is None:
        return None
    return round(own_best - pole_best, 3)


def _qual_best_seconds(q: dict[str, Any]) -> float | None:
    for k in ("q3", "q2", "q1"):
        t = q.get(k)
        if not t:
            continue
        try:
            if ":" in t:
                m, s = t.split(":", 1)
                return round(int(m) * 60 + float(s), 3)
            return round(float(t), 3)
        except (ValueError, TypeError):
            continue
    return None


def compute_team_race_metrics(
    laps: pd.DataFrame,
    results: list[dict[str, Any]],
    pit_stops: list[dict[str, Any]],
    year: int,
    round_number: int,
    weather: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One TEAM_METRICS record per team per race.

    Fields:
      avg_race_pace_s, best_lap_s, points_scored, drivers_finished,
      pit_stop_count, avg_pit_duration_s, drivers, status_summary
    """
    if not results:
        return []

    by_team: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "points": 0.0,
            "drivers": [],
            "finished": 0,
            "best_lap_s": None,
            "lap_times": [],
            "status_summary": defaultdict(int),
            "pit_stops": [],
        }
    )

    for r in results:
        team_code = normalise_team_code(r.get("constructor_id", ""))
        bucket = by_team[team_code]
        bucket["points"] += float(r.get("points") or 0)
        bucket["drivers"].append(r.get("driver_code"))
        if r.get("status") == "Finished" or (r.get("status") or "").startswith("+"):
            bucket["finished"] += 1
        bucket["status_summary"][r.get("status") or "Unknown"] += 1

    if not laps.empty and "LapTimeSeconds" in laps.columns:
        for team_name, group in laps.groupby("Team"):
            team_code = normalise_team_code(team_name)
            valid = group["LapTimeSeconds"].dropna()
            if valid.empty:
                continue
            by_team[team_code]["lap_times"].extend(valid.tolist())
            by_team[team_code]["best_lap_s"] = float(valid.min())

    # Pit stops — driver_id → team mapping comes from results
    driver_team = {r.get("driver_id"): normalise_team_code(r.get("constructor_id", "")) for r in results}
    for stop in pit_stops:
        team_code = driver_team.get(stop["driver_id"])
        if not team_code:
            continue
        if stop.get("duration_seconds"):
            by_team[team_code]["pit_stops"].append(stop["duration_seconds"])

    flags = compute_race_flags(laps, weather)
    items = []
    for team_code, data in by_team.items():
        lap_arr = np.array(data["lap_times"]) if data["lap_times"] else np.array([])
        items.append(
            {
                "PK": f"RACE#{year}#{round_number}",
                "SK": f"TEAM_METRICS#{team_code}",
                "TeamCode": team_code,
                "TrackKey": f"{year}#{round_number}",
                "PointsScored": round(data["points"], 1),
                "DriversFinished": data["finished"],
                "BestLapSeconds": round(float(lap_arr.min()), 3) if lap_arr.size else None,
                "AvgRacePaceSeconds": round(float(np.mean(lap_arr)), 3) if lap_arr.size else None,
                "MedianRacePaceSeconds": round(float(np.median(lap_arr)), 3) if lap_arr.size else None,
                "LapPaceStdDev": round(float(np.std(lap_arr)), 4) if lap_arr.size else None,
                "Drivers": data["drivers"],
                "StatusSummary": dict(data["status_summary"]),
                "PitStopCount": len(data["pit_stops"]),
                "AvgPitDurationSeconds": round(float(np.mean(data["pit_stops"])), 3)
                if data["pit_stops"] else None,
                "FastestPitSeconds": round(float(min(data["pit_stops"])), 3)
                if data["pit_stops"] else None,
                "WetRace": flags["WetRace"],
                "SafetyCarLapPct": flags["SafetyCarLapPct"],
            }
        )
    return items


def compute_tyre_degradation(laps: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Per-driver lap-time degradation rate per compound (sec / lap of life).

    Uses a simple linear regression on (TyreLife, LapTimeSeconds) within each
    stint. Skips compounds with fewer than 4 valid laps.
    """
    if laps.empty or "LapTimeSeconds" not in laps.columns or "Compound" not in laps.columns:
        return {}

    out: dict[str, dict[str, float]] = {}
    for (driver, compound), grp in laps.groupby(["Driver", "Compound"]):
        valid = grp.dropna(subset=["LapTimeSeconds", "TyreLife"])
        if len(valid) < 4:
            continue
        x = valid["TyreLife"].astype(float).to_numpy()
        y = valid["LapTimeSeconds"].astype(float).to_numpy()
        slope, _intercept = np.polyfit(x, y, 1)
        out.setdefault(driver, {})[compound] = round(float(slope), 4)
    return out


def compute_sector_rankings(laps: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Each driver's rank (1 = fastest) in each sector across the session."""
    rankings: dict[str, dict[str, int]] = {}
    if laps.empty:
        return rankings

    for sector in ("Sector1TimeSeconds", "Sector2TimeSeconds", "Sector3TimeSeconds"):
        if sector not in laps.columns:
            continue
        best = laps.dropna(subset=[sector]).groupby("Driver")[sector].min().sort_values()
        for rank, (driver, _) in enumerate(best.items(), start=1):
            rankings.setdefault(driver, {})[sector.replace("TimeSeconds", "")] = rank
    return rankings
