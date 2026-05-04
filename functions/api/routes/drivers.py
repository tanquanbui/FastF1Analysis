"""Driver routes."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_index


@route("/drivers/{code}")
def get_driver_profile(code: str, event: dict[str, Any]) -> dict[str, Any]:
    """Aggregate RESULT and LAP records via the DriverRaceIndex GSI."""
    items = query_index("DriverRaceIndex", "DriverCode", code.upper())
    if not items:
        raise KeyError(f"driver {code} not found")

    results = [i for i in items if i["SK"].startswith("RESULT#")]
    standings = [i for i in items if i["SK"].startswith("DRIVER#")]
    laps = [i for i in items if i["SK"].startswith("LAP#")]

    podiums = sum(1 for r in results if (r.get("Position") or 99) <= 3)
    wins = sum(1 for r in results if r.get("Position") == 1)
    total_points = sum(r.get("Points") or 0 for r in results)

    return {
        "driver_code": code.upper(),
        "driver_name": results[0].get("DriverName") if results else None,
        "team_code": results[-1].get("TeamCode") if results else None,
        "races_entered": len(results),
        "wins": wins,
        "podiums": podiums,
        "total_points": total_points,
        "results": sorted(results, key=lambda r: r.get("RaceKey") or ""),
        "standings_history": sorted(standings, key=lambda r: r.get("PK", "")),
        "lap_count": len(laps),
    }
