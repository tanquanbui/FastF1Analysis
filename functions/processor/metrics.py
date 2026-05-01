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


def compute_team_race_metrics(
    laps: pd.DataFrame,
    results: list[dict[str, Any]],
    pit_stops: list[dict[str, Any]],
    year: int,
    round_number: int,
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
