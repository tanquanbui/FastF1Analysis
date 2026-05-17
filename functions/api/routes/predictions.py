"""Predictions routes — driver-level + team-level prediction reports."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_by_pk


@route("/predictions/{year}/{round}")
def get_predictions(year: str, round: str, event: dict[str, Any]) -> dict[str, Any]:
    """Team-level reports (one per team, sorted by predicted finish)."""
    items = query_by_pk(f"PREDICTION#{year}#{round}", sk_prefix="TEAM#")
    if not items:
        raise KeyError(f"no predictions for {year}#{round}")

    return {
        "year": int(year),
        "round": int(round),
        "race_name": (items[0].get("Report") or {}).get("race"),
        "team_reports": sorted(
            [i.get("Report") or {} for i in items],
            key=lambda r: (r.get("prediction", {}).get("race", {}).get("predicted_position", 99)),
        ),
    }


@route("/predictions/{year}/{round}/drivers")
def get_driver_predictions(year: str, round: str, event: dict[str, Any]) -> dict[str, Any]:
    """Per-driver scored leaderboard with the full signal breakdown."""
    items = query_by_pk(f"PREDICTION#{year}#{round}", sk_prefix="DRIVER#")
    if not items:
        raise KeyError(f"no driver predictions for {year}#{round}")
    drivers = sorted(items, key=lambda i: int(i.get("PredictedPosition") or 99))
    return {
        "year": int(year),
        "round": int(round),
        "drivers": drivers,
    }
