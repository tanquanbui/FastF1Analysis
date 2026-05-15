"""Upgrades route — detected upgrade events for a team in a given season."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_by_pk


@route("/upgrades/{year}/{team_code}")
def get_upgrades(year: str, team_code: str, event: dict[str, Any]) -> dict[str, Any]:
    team_code = team_code.upper()
    items = query_by_pk(f"UPGRADE#{year}#{team_code}", sk_prefix="RACE#")
    return {
        "year": int(year),
        "team_code": team_code,
        "events": sorted(
            (
                {
                    "round": int(item.get("Round") or 0),
                    "affected_dimensions": list(item.get("AffectedDimensions") or []),
                    "delta": {k: float(v) for k, v in (item.get("Delta") or {}).items()},
                    "confidence": float(item.get("Confidence") or 0),
                    "notes": item.get("Notes") or "",
                }
                for item in items
            ),
            key=lambda u: u["round"],
        ),
    }
