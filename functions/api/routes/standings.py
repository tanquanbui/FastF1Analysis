"""Standings routes."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_by_pk


@route("/standings/{year}/{round}")
def get_standings(year: str, round: str, event: dict[str, Any]) -> dict[str, Any]:
    """Return both constructor and driver standings at a given round."""
    items = query_by_pk(f"STANDINGS#{year}#{round}")
    if not items:
        raise KeyError(f"standings {year}#{round} not found")

    constructors = sorted(
        (i for i in items if i["SK"].startswith("CONSTRUCTOR#")),
        key=lambda i: i.get("Position") or 99,
    )
    drivers = sorted(
        (i for i in items if i["SK"].startswith("DRIVER#")),
        key=lambda i: i.get("Position") or 99,
    )
    return {
        "year": int(year),
        "round": int(round),
        "constructors": constructors,
        "drivers": drivers,
    }
