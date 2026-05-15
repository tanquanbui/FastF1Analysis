"""Fingerprint route — current fingerprint plus per-round series for the season."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import route

from ._common import query_by_pk

FINGERPRINT_DIMENSIONS = [
    "straight_line_speed",
    "high_speed_cornering",
    "low_speed_cornering",
    "tyre_management",
    "qualifying_pace",
    "race_pace_conversion",
    "tyre_strategy_execution",
    "wet_weather_performance",
]


@route("/team/{code}/fingerprint")
def get_team_fingerprint(code: str, event: dict[str, Any]) -> dict[str, Any]:
    code = code.upper()
    year = (event.get("queryStringParameters") or {}).get("year") or datetime.now(timezone.utc).year
    items = query_by_pk(f"FINGERPRINT#{year}#{code}", sk_prefix="TRACK#")
    if not items:
        raise KeyError(f"no fingerprints for {code} in {year}")

    items.sort(key=lambda i: int(i.get("Round") or 0))
    latest = items[-1]

    return {
        "team_code": code,
        "year": int(year),
        "latest_round": int(latest.get("Round") or 0),
        "dimensions": {dim: float(latest.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS},
        "history": [
            {
                "round": int(item.get("Round") or 0),
                "dimensions": {dim: float(item.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS},
            }
            for item in items
        ],
    }
