"""Race routes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app import route

from ._common import query_by_pk


def _fetch_round_podium(year: str, round_num: int) -> dict[str, Any] | None:
    items = query_by_pk(f"RACE#{year}#{round_num}", sk_prefix="RESULT#", limit=30)
    if not items:
        return None
    podium = sorted(
        (i for i in items if isinstance(i.get("Position"), int)),
        key=lambda i: i["Position"],
    )[:3]
    return {
        "year": int(year),
        "round": round_num,
        "podium": [
            {
                "position": p["Position"],
                "driver_code": p.get("DriverCode"),
                "team_code": p.get("TeamCode"),
                "points": p.get("Points"),
            }
            for p in podium
        ],
        "entries": len(items),
    }


@route("/races/{year}")
def list_season_races(year: str, event: dict[str, Any]) -> dict[str, Any]:
    """Parallelise the per-round DynamoDB queries so the season hub loads
    in ~200ms instead of ~2-3s.
    """
    rounds: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_fetch_round_podium, year, r): r for r in range(1, 25)}
        for future in as_completed(futures):
            result = future.result()
            if result:
                rounds[result["round"]] = result

    return {
        "year": int(year),
        "races": sorted(rounds.values(), key=lambda r: r["round"]),
    }


@route("/races/{year}/{round}")
def get_race_detail(year: str, round: str, event: dict[str, Any]) -> dict[str, Any]:
    """Full race detail — results, lap log, team metrics."""
    pk = f"RACE#{year}#{round}"
    all_items = query_by_pk(pk)
    if not all_items:
        raise KeyError(f"race {pk} not found")

    results = [i for i in all_items if i["SK"].startswith("RESULT#")]
    laps = [i for i in all_items if i["SK"].startswith("LAP#")]
    team_metrics = [i for i in all_items if i["SK"].startswith("TEAM_METRICS#")]

    return {
        "year": int(year),
        "round": int(round),
        "results": sorted(results, key=lambda r: (r.get("Position") or 99)),
        "laps": sorted(laps, key=lambda r: (r.get("DriverCode"), r.get("LapNumber") or 0)),
        "team_metrics": sorted(team_metrics, key=lambda r: -(r.get("PointsScored") or 0)),
    }
