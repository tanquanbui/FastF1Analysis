"""Pure-function transformers — clean raw FastF1 / Ergast payloads into the
shapes the metrics module and DynamoDB writer expect.

Anything statistical lives in metrics.py; this module is just shaping.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical team-code mapping — Ergast uses constructorIds like "red_bull",
# FastF1 uses team names like "Red Bull Racing". We normalise on a 3-letter
# code that becomes the DynamoDB PK suffix.
TEAM_CODE_MAP = {
    "red_bull": "RBR",
    "red bull racing": "RBR",
    "red bull": "RBR",
    "mclaren": "MCL",
    "ferrari": "FER",
    "mercedes": "MER",
    "aston_martin": "AST",
    "aston martin": "AST",
    "alpine": "ALP",
    "williams": "WIL",
    "rb": "RB",
    "racing bulls": "RB",
    "kick_sauber": "SAU",
    "kick sauber": "SAU",
    "stake f1 team kick sauber": "SAU",
    "haas": "HAA",
    "alfa": "SAU",
}


def normalise_team_code(team: str) -> str:
    """Map any Ergast/FastF1 team string to the canonical 3-letter code."""
    if not team:
        return "UNK"
    key = team.strip().lower()
    return TEAM_CODE_MAP.get(key, key[:3].upper())


def clean_lap_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop in/out laps, normalise lap times to floating-point seconds.

    Returns a new DataFrame; never mutates the input.
    """
    if df.empty:
        return df.copy()

    out = df.copy()
    # Convert any Timedelta columns to seconds.
    for col in ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]:
        if col in out.columns:
            out[col + "Seconds"] = _timedelta_to_seconds(out[col])

    # Drop laps with pit in/out (not representative of race pace).
    if "PitInTime" in out.columns:
        out = out[out["PitInTime"].isna()]
    if "PitOutTime" in out.columns:
        out = out[out["PitOutTime"].isna()]

    # Drop laps under non-green flags (TrackStatus != "1" means yellow/red/SC).
    if "TrackStatus" in out.columns:
        out = out[out["TrackStatus"].astype(str) == "1"]

    return out.reset_index(drop=True)


def _timedelta_to_seconds(series: pd.Series) -> pd.Series:
    """Coerce a Timedelta or string column to seconds as floats."""
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds()
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def aggregate_driver_lap_summary(laps: pd.DataFrame) -> list[dict[str, Any]]:
    """One row per driver, aggregating across the session."""
    if laps.empty or "LapTimeSeconds" not in laps.columns:
        return []

    grouped = laps.groupby("Driver", as_index=False).agg(
        team=("Team", "first"),
        laps_completed=("LapNumber", "max"),
        fastest_lap_s=("LapTimeSeconds", "min"),
        avg_lap_s=("LapTimeSeconds", "mean"),
        median_lap_s=("LapTimeSeconds", "median"),
        std_lap_s=("LapTimeSeconds", "std"),
    )

    records = []
    for _, row in grouped.iterrows():
        records.append(
            {
                "driver_code": row["Driver"],
                "team_code": normalise_team_code(row["team"]),
                "team_name": row["team"],
                "laps_completed": int(row["laps_completed"]) if pd.notna(row["laps_completed"]) else 0,
                "fastest_lap_s": round(float(row["fastest_lap_s"]), 3) if pd.notna(row["fastest_lap_s"]) else None,
                "avg_lap_s": round(float(row["avg_lap_s"]), 3) if pd.notna(row["avg_lap_s"]) else None,
                "median_lap_s": round(float(row["median_lap_s"]), 3) if pd.notna(row["median_lap_s"]) else None,
                "lap_time_stddev_s": round(float(row["std_lap_s"]), 4)
                if pd.notna(row["std_lap_s"]) else None,
            }
        )
    return records


def laps_to_dynamo_records(laps: pd.DataFrame, year: int, round_number: int) -> list[dict[str, Any]]:
    """Turn cleaned lap DataFrame into DynamoDB PutItem records.

    Each lap becomes: ``PK=RACE#{year}#{round}  SK=LAP#{driver}#{lap:03d}``.
    """
    if laps.empty:
        return []

    items = []
    for row in laps.to_dict(orient="records"):
        lap_no = row.get("LapNumber")
        driver = row.get("Driver")
        if not driver or pd.isna(lap_no):
            continue
        items.append(
            {
                "PK": f"RACE#{year}#{round_number}",
                "SK": f"LAP#{driver}#{int(lap_no):03d}",
                "DriverCode": driver,
                "RaceKey": f"{year}#{round_number}",
                "TeamCode": normalise_team_code(row.get("Team", "")),
                "LapNumber": int(lap_no),
                "LapTimeSeconds": _safe_float(row.get("LapTimeSeconds")),
                "Sector1Seconds": _safe_float(row.get("Sector1TimeSeconds")),
                "Sector2Seconds": _safe_float(row.get("Sector2TimeSeconds")),
                "Sector3Seconds": _safe_float(row.get("Sector3TimeSeconds")),
                "Compound": row.get("Compound"),
                "TyreLife": _safe_int(row.get("TyreLife")),
                "Position": _safe_int(row.get("Position")),
                "Stint": _safe_int(row.get("Stint")),
                "IsPersonalBest": bool(row.get("IsPersonalBest")) if row.get("IsPersonalBest") is not None else None,
                "TrackStatus": row.get("TrackStatus"),
                "SpeedI1": _safe_float(row.get("SpeedI1")),
                "SpeedI2": _safe_float(row.get("SpeedI2")),
                "SpeedFL": _safe_float(row.get("SpeedFL")),
                "SpeedST": _safe_float(row.get("SpeedST")),
            }
        )
    return items


def results_to_dynamo_records(
    results: list[dict[str, Any]], year: int, round_number: int
) -> list[dict[str, Any]]:
    """Ergast race-result rows → DynamoDB items."""
    items = []
    for r in results:
        code = r.get("driver_code") or r.get("driver_id", "").upper()[:3]
        items.append(
            {
                "PK": f"RACE#{year}#{round_number}",
                "SK": f"RESULT#{code}",
                "DriverCode": code,
                "RaceKey": f"{year}#{round_number}",
                "TeamCode": normalise_team_code(r.get("constructor_id", "")),
                "Position": r.get("position"),
                "PositionText": r.get("position_text"),
                "Grid": r.get("grid"),
                "Laps": r.get("laps"),
                "Status": r.get("status"),
                "Points": r.get("points"),
                "DriverName": r.get("driver_name"),
                "ConstructorName": r.get("constructor_name"),
                "TimeMillis": r.get("time_millis"),
                "FastestLapTime": r.get("fastest_lap_time"),
                "FastestLapRank": r.get("fastest_lap_rank"),
                "FastestLapSpeedKph": r.get("fastest_lap_speed_kph"),
            }
        )
    return items


def qualifying_to_dynamo_records(
    qualifying: list[dict[str, Any]], year: int, round_number: int
) -> list[dict[str, Any]]:
    """Ergast qualifying rows → DynamoDB QUALIFYING# items."""
    items: list[dict[str, Any]] = []
    pole_time = _q_seconds(qualifying[0]) if qualifying else None
    for q in qualifying:
        code = q.get("driver_code") or (q.get("driver_name") or "").upper()[:3]
        q_best = _q_seconds(q)
        items.append(
            {
                "PK": f"RACE#{year}#{round_number}",
                "SK": f"QUALIFYING#{code}",
                "DriverCode": code,
                "RaceKey": f"{year}#{round_number}",
                "TeamCode": normalise_team_code(q.get("constructor", "")),
                "Position": q.get("position"),
                "DriverName": q.get("driver_name"),
                "Q1": q.get("q1"),
                "Q2": q.get("q2"),
                "Q3": q.get("q3"),
                "BestSeconds": q_best,
                "GapToPole": round(q_best - pole_time, 3) if q_best and pole_time else None,
            }
        )
    return items


def _q_seconds(q: dict[str, Any]) -> float | None:
    """Convert the fastest of Q1/Q2/Q3 to seconds."""
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


def standings_to_dynamo_records(
    constructor_standings: list[dict[str, Any]],
    driver_standings: list[dict[str, Any]],
    year: int,
    round_number: int,
) -> list[dict[str, Any]]:
    """Standings → ``PK=STANDINGS#{year}#{round}``."""
    items = []
    for s in constructor_standings:
        team_code = normalise_team_code(s["constructor_id"])
        items.append(
            {
                "PK": f"STANDINGS#{year}#{round_number}",
                "SK": f"CONSTRUCTOR#{team_code}",
                "TeamCode": team_code,
                "TrackKey": "season",
                "Position": s["position"],
                "Points": s["points"],
                "Wins": s["wins"],
                "ConstructorName": s["constructor_name"],
            }
        )
    for s in driver_standings:
        items.append(
            {
                "PK": f"STANDINGS#{year}#{round_number}",
                "SK": f"DRIVER#{s['driver_code']}",
                "DriverCode": s["driver_code"],
                "RaceKey": f"{year}#{round_number}",
                "Position": s["position"],
                "Points": s["points"],
                "Wins": s["wins"],
                "DriverName": s["driver_name"],
                "TeamCode": normalise_team_code(s.get("constructor_id") or ""),
            }
        )
    return items


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
