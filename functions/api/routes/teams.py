"""Team routes."""
from __future__ import annotations

from typing import Any

from app import route

from ._common import query_index


@route("/teams/{code}")
def get_team_profile(code: str, event: dict[str, Any]) -> dict[str, Any]:
    """Team race metrics + standings history via the TeamTrackIndex GSI."""
    items = query_index("TeamTrackIndex", "TeamCode", code.upper())
    if not items:
        raise KeyError(f"team {code} not found")

    team_metrics = [i for i in items if i["SK"].startswith("TEAM_METRICS#")]
    standings = [i for i in items if i["SK"].startswith("CONSTRUCTOR#")]
    fingerprints = [i for i in items if i["PK"].startswith("FINGERPRINT#")]

    total_points = sum(m.get("PointsScored") or 0 for m in team_metrics)
    races = len(team_metrics)

    return {
        "team_code": code.upper(),
        "races_completed": races,
        "total_points": total_points,
        "team_metrics": sorted(team_metrics, key=lambda i: i.get("TrackKey") or ""),
        "standings_history": sorted(standings, key=lambda i: i.get("PK") or ""),
        "fingerprint_count": len(fingerprints),
    }
