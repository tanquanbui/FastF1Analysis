"""Predictions route — reads cached predictor output keyed by year+round."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_by_pk


@route("/predictions/{year}/{round}")
def get_predictions(year: str, round: str, event: dict[str, Any]) -> dict[str, Any]:
    items = query_by_pk(f"PREDICTION#{year}#{round}", sk_prefix="TEAM#")
    if not items:
        raise KeyError(f"no predictions written for {year}#{round}")

    return {
        "year": int(year),
        "round": int(round),
        "race_name": (items[0].get("Report") or {}).get("race"),
        "team_reports": sorted(
            [i.get("Report") or {} for i in items],
            key=lambda r: (r.get("prediction", {}).get("race", {}).get("predicted_position", 99)),
        ),
    }
