"""Ergast / jolpi.ca mirror client.

The public Ergast API at ergast.com is being deprecated; jolpi.ca maintains a
drop-in compatible mirror. All endpoints return JSON shaped identically to
classic Ergast: results live under ``MRData.RaceTable.Races[*]``.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("ERGAST_BASE_URL", "https://api.jolpi.ca/ergast/f1")
DEFAULT_TIMEOUT = 30
USER_AGENT = "PitStopAnalytics/1.0 (+https://github.com/quantanbui/FastF1Analysis)"


class ErgastError(RuntimeError):
    """Raised when the Ergast mirror returns an unrecoverable error."""


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=15),
    retry=retry_if_exception_type((requests.RequestException, ErgastError)),
    reraise=True,
)
def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue a GET to the Ergast mirror and return the parsed MRData payload."""
    url = f"{BASE_URL}/{path.lstrip('/')}.json"
    logger.debug("ergast GET %s params=%s", url, params)
    response = requests.get(
        url,
        params=params,
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if response.status_code >= 500:
        raise ErgastError(f"upstream {response.status_code} from {url}")
    response.raise_for_status()
    return response.json().get("MRData", {})


def get_race_schedule(year: int) -> list[dict[str, Any]]:
    """Return the season race calendar."""
    data = _get(f"{year}", params={"limit": 100})
    races = data.get("RaceTable", {}).get("Races", [])
    return [
        {
            "year": int(race["season"]),
            "round": int(race["round"]),
            "name": race["raceName"],
            "circuit_id": race["Circuit"]["circuitId"],
            "circuit_name": race["Circuit"]["circuitName"],
            "country": race["Circuit"]["Location"]["country"],
            "locality": race["Circuit"]["Location"]["locality"],
            "date": race["date"],
            "time": race.get("time"),
        }
        for race in races
    ]


def get_race_results(year: int, round_number: int) -> list[dict[str, Any]]:
    """Return per-driver race results for a single round."""
    data = _get(f"{year}/{round_number}/results", params={"limit": 100})
    races = data.get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    results = races[0].get("Results", [])
    return [_normalise_result(r) for r in results]


def get_qualifying_results(year: int, round_number: int) -> list[dict[str, Any]]:
    """Return qualifying classification (Q1/Q2/Q3 times)."""
    data = _get(f"{year}/{round_number}/qualifying", params={"limit": 100})
    races = data.get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    return [
        {
            "position": int(q["position"]),
            "driver_code": q["Driver"]["code"],
            "driver_name": f"{q['Driver']['givenName']} {q['Driver']['familyName']}",
            "constructor": q["Constructor"]["constructorId"],
            "q1": q.get("Q1"),
            "q2": q.get("Q2"),
            "q3": q.get("Q3"),
        }
        for q in races[0].get("QualifyingResults", [])
    ]


def get_constructor_standings(year: int, round_number: int) -> list[dict[str, Any]]:
    """Constructor standings as of a specific round."""
    data = _get(f"{year}/{round_number}/constructorStandings", params={"limit": 100})
    standings_lists = data.get("StandingsTable", {}).get("StandingsLists", [])
    if not standings_lists:
        return []
    return [
        {
            "position": int(s["position"]),
            "constructor_id": s["Constructor"]["constructorId"],
            "constructor_name": s["Constructor"]["name"],
            "nationality": s["Constructor"]["nationality"],
            "points": float(s["points"]),
            "wins": int(s["wins"]),
        }
        for s in standings_lists[0].get("ConstructorStandings", [])
    ]


def get_driver_standings(year: int, round_number: int) -> list[dict[str, Any]]:
    """Driver standings as of a specific round."""
    data = _get(f"{year}/{round_number}/driverStandings", params={"limit": 100})
    standings_lists = data.get("StandingsTable", {}).get("StandingsLists", [])
    if not standings_lists:
        return []
    return [
        {
            "position": int(s["position"]),
            "driver_code": s["Driver"]["code"],
            "driver_name": f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
            "constructor_id": s["Constructors"][0]["constructorId"] if s.get("Constructors") else None,
            "points": float(s["points"]),
            "wins": int(s["wins"]),
        }
        for s in standings_lists[0].get("DriverStandings", [])
    ]


def get_pit_stop_data(year: int, round_number: int) -> list[dict[str, Any]]:
    """Pit stop log for a race (driver / stop number / lap / duration)."""
    data = _get(f"{year}/{round_number}/pitstops", params={"limit": 200})
    races = data.get("RaceTable", {}).get("Races", [])
    if not races:
        return []
    return [
        {
            "driver_id": p["driverId"],
            "stop": int(p["stop"]),
            "lap": int(p["lap"]),
            "time_of_day": p.get("time"),
            "duration_seconds": _parse_duration(p.get("duration")),
        }
        for p in races[0].get("PitStops", [])
    ]


def _parse_duration(value: str | None) -> float | None:
    """Parse Ergast duration strings. Most look like ``23.456`` (seconds),
    but slow stops or pit-lane-traffic timings come back as ``mm:ss.ms``.
    """
    if not value:
        return None
    try:
        if ":" in value:
            parts = value.split(":")
            return round(int(parts[0]) * 60 + float(parts[1]), 3)
        return float(value)
    except (ValueError, IndexError):
        return None


def _normalise_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce one Ergast race-result row into our DynamoDB-friendly shape."""
    fastest_lap = raw.get("FastestLap") or {}
    return {
        "position": int(raw["position"]) if raw.get("position", "").isdigit() else None,
        "position_text": raw["positionText"],
        "grid": int(raw["grid"]),
        "laps": int(raw["laps"]),
        "status": raw["status"],
        "points": float(raw["points"]),
        "driver_code": raw["Driver"].get("code"),
        "driver_id": raw["Driver"]["driverId"],
        "driver_name": f"{raw['Driver']['givenName']} {raw['Driver']['familyName']}",
        "constructor_id": raw["Constructor"]["constructorId"],
        "constructor_name": raw["Constructor"]["name"],
        "time_millis": int(raw["Time"]["millis"]) if raw.get("Time") else None,
        "fastest_lap_rank": int(fastest_lap["rank"]) if fastest_lap.get("rank") else None,
        "fastest_lap_time": fastest_lap.get("Time", {}).get("time"),
        "fastest_lap_speed_kph": float(fastest_lap.get("AverageSpeed", {}).get("speed"))
        if fastest_lap.get("AverageSpeed", {}).get("speed")
        else None,
    }
