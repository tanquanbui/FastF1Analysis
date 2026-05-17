"""Qualifying route — returns Q1/Q2/Q3 times per driver for a race."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_by_pk


@route("/qualifying/{year}/{round}")
def get_qualifying(year: str, round: str, event: dict[str, Any]) -> dict[str, Any]:
    items = query_by_pk(f"RACE#{year}#{round}", sk_prefix="QUALIFYING#")
    if not items:
        raise KeyError(f"no qualifying for {year}#{round}")
    return {
        "year": int(year),
        "round": int(round),
        "qualifying": sorted(items, key=lambda i: int(i.get("Position") or 99)),
    }
