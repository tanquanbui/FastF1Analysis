"""Championship route — returns the latest Monte Carlo simulation result."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_by_pk


@route("/championship/{year}/scenarios")
def get_championship_scenarios(year: str, event: dict[str, Any]) -> dict[str, Any]:
    items = query_by_pk(f"SEASON_SIM#{year}", sk_prefix="ROUND#")
    if not items:
        raise KeyError(f"no championship simulation for {year}")
    latest = max(items, key=lambda i: int(i.get("Round") or 0))
    return {
        "year": int(year),
        "as_of_round": int(latest.get("Round") or 0),
        **(latest.get("MonteCarlo") or {}),
    }
