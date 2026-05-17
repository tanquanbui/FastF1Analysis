"""Predictor Lambda — driver-level race forecaster.

For every driver in the upcoming race we compute six signals (qualifying,
historical at circuit, recent form, overtaking skill, reliability, track fit)
and blend them into a 0-100 score. The team prediction is the position of the
team's best-scoring driver.

Event payload:
    {"year": 2024, "round": 3, "circuit_key": "albert_park"}
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, str(Path(__file__).parent))

from championship_sim import simulate_championship  # noqa: E402
from circuit_profiler import (  # noqa: E402
    FINGERPRINT_DIMENSIONS,
    compute_track_compatibility,
    get_profile,
)
from scorer import score_driver  # noqa: E402
from upgrade_detector import project_upgrade_impact  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "")
table = dynamodb.Table(TABLE_NAME)

RECENT_WINDOW = 5
HISTORICAL_WINDOW_YEARS = 3


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point."""
    year = int(event.get("year") or date.today().year)
    round_number = int(event.get("round") or _next_round(year))
    circuit_key = event.get("circuit_key") or "monza"
    profile = get_profile(circuit_key) or {dim: 0.5 for dim in FINGERPRINT_DIMENSIONS}
    logger.info("predicting %s round %s circuit=%s", year, round_number, circuit_key)

    # 1. Roster for this race — look up every driver that competed.
    roster = _race_roster(year, round_number)
    if not roster:
        logger.warning("no roster found for %s-%s; backing off to standings", year, round_number)
        roster = _roster_from_standings(year, round_number - 1)
    if not roster:
        return {"statusCode": 200, "body": {"year": year, "round": round_number, "drivers": 0}}

    # 2. Pre-compute per-team fingerprint × circuit profile for the track fit signal.
    teams = sorted({d["team_code"] for d in roster})
    track_fit_by_team = {
        team: compute_track_compatibility(
            _load_fingerprint(team, year, round_number - 1),
            profile,
        )["overall_score"]
        for team in teams
    }

    # 3. Quali results for this race, if available.
    qualifying = {q["DriverCode"]: q for q in _load_qualifying(year, round_number)}

    # 4. Score each driver.
    driver_scores: list[dict[str, Any]] = []
    for driver in roster:
        code = driver["driver_code"]
        team_code = driver["team_code"]
        q_pos = qualifying.get(code, {}).get("Position")

        # Historical positions at this same round in prior seasons.
        hist_positions = _driver_positions_at_round(
            code, round_number, year - HISTORICAL_WINDOW_YEARS, year - 1,
        )
        # Recent form — last 5 finishing positions this season.
        recent_positions = _driver_recent_positions(code, year, round_number, RECENT_WINDOW)
        # Grid → finish deltas over last 10 races (any year).
        gain_history = _driver_grid_to_finish_history(code, year, round_number, lookback=10)
        # DNF rate over last 10 races.
        dnf_rate = _driver_dnf_rate(code, year, round_number, lookback=10)

        score = score_driver(
            qualifying_pos=int(q_pos) if q_pos is not None else None,
            historical_positions=hist_positions,
            recent_positions=recent_positions,
            grid_to_finish_history=gain_history,
            dnf_rate=dnf_rate,
            track_fit_score=track_fit_by_team.get(team_code),
            wet_likely=False,
            wet_history_positions=None,
            field_size=20,
        )

        driver_scores.append({
            "driver_code": code,
            "driver_name": driver.get("driver_name"),
            "team_code": team_code,
            "score_breakdown": score,
            "qualifying_position": int(q_pos) if q_pos is not None else None,
            "input_data": {
                "historical_positions": hist_positions,
                "recent_positions": recent_positions,
                "grid_to_finish_history": gain_history,
                "dnf_rate": round(dnf_rate, 3) if dnf_rate is not None else None,
                "track_fit": round(track_fit_by_team.get(team_code, 0), 1),
            },
        })

    # 5. Rank by combined score.
    driver_scores.sort(key=lambda d: -d["score_breakdown"]["combined"])
    for idx, d in enumerate(driver_scores):
        d["predicted_position"] = idx + 1

    # 6. Aggregate team prediction = best driver position.
    team_reports = _build_team_reports(
        driver_scores, year, round_number, circuit_key, profile, track_fit_by_team,
    )

    # 7. Persist driver predictions and team reports.
    _persist(year, round_number, driver_scores, team_reports)

    return {
        "statusCode": 200,
        "body": {
            "year": year,
            "round": round_number,
            "circuit": circuit_key,
            "drivers_scored": len(driver_scores),
            "team_reports": len(team_reports),
            "top_prediction": driver_scores[0]["driver_code"] if driver_scores else None,
        },
    }


# ---------------------- data loaders ----------------------

def _race_roster(year: int, round_number: int) -> list[dict[str, Any]]:
    """Pull the driver list for the upcoming race. Falls back to last race's
    RESULT items (most accurate roster) before checking driver standings."""
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{round_number}") & Key("SK").begins_with("RESULT#"),
    )
    items = response.get("Items", [])
    if items:
        return [
            {
                "driver_code": i.get("DriverCode"),
                "driver_name": i.get("DriverName"),
                "team_code": i.get("TeamCode"),
            }
            for i in items if i.get("DriverCode")
        ]
    return []


def _roster_from_standings(year: int, round_number: int) -> list[dict[str, Any]]:
    if round_number <= 0:
        return []
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"STANDINGS#{year}#{round_number}") & Key("SK").begins_with("DRIVER#"),
    )
    return [
        {
            "driver_code": i.get("DriverCode"),
            "driver_name": i.get("DriverName"),
            "team_code": i.get("TeamCode"),
        }
        for i in response.get("Items", [])
        if i.get("DriverCode")
    ]


def _load_qualifying(year: int, round_number: int) -> list[dict[str, Any]]:
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{round_number}") & Key("SK").begins_with("QUALIFYING#"),
    )
    return response.get("Items", [])


def _driver_positions_at_round(
    driver: str, round_number: int, start_year: int, end_year: int,
) -> list[int]:
    """Driver's finishing position at the same round number, across prior seasons."""
    positions: list[int] = []
    for y in range(start_year, end_year + 1):
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"RACE#{y}#{round_number}") & Key("SK").eq(f"RESULT#{driver}"),
        )
        for item in response.get("Items", []):
            pos = item.get("Position")
            if isinstance(pos, (int, float, Decimal)) and pos > 0:
                positions.append(int(pos))
    return positions


def _driver_recent_positions(
    driver: str, year: int, round_number: int, window: int,
) -> list[int]:
    """Last `window` finishing positions this season."""
    positions = []
    for r in range(max(1, round_number - window), round_number):
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{r}") & Key("SK").eq(f"RESULT#{driver}"),
        )
        for item in response.get("Items", []):
            pos = item.get("Position")
            if isinstance(pos, (int, float, Decimal)) and pos > 0:
                positions.append(int(pos))
    return positions


def _driver_grid_to_finish_history(
    driver: str, year: int, round_number: int, lookback: int = 10,
) -> list[int]:
    """Positions gained from grid → finish across the last N races."""
    gains = []
    rounds_back = list(range(max(1, round_number - lookback), round_number))
    for r in rounds_back:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{r}") & Key("SK").eq(f"DRIVER_METRICS#{driver}"),
        )
        for item in response.get("Items", []):
            delta = item.get("GridToFinishDelta")
            if delta is not None:
                gains.append(int(delta))
    return gains


def _driver_dnf_rate(driver: str, year: int, round_number: int, lookback: int = 10) -> float | None:
    """DNF / DNS / accidents over the last N races. None when no data."""
    starts = 0
    dnf = 0
    rounds_back = list(range(max(1, round_number - lookback), round_number))
    for r in rounds_back:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{r}") & Key("SK").eq(f"RESULT#{driver}"),
        )
        for item in response.get("Items", []):
            starts += 1
            status = (item.get("Status") or "").lower()
            if status != "finished" and not status.startswith("+"):
                dnf += 1
    return dnf / starts if starts else None


def _load_fingerprint(team_code: str, year: int, latest_round: int) -> dict[str, float]:
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"FINGERPRINT#{year}#{team_code}"),
    )
    items = sorted(
        response.get("Items", []),
        key=lambda i: int(i.get("Round") or 0),
        reverse=True,
    )
    for item in items:
        if int(item.get("Round") or 0) <= latest_round:
            return {dim: float(item.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS}
    return {dim: 50.0 for dim in FINGERPRINT_DIMENSIONS}


# ---------------------- reports ----------------------

def _build_team_reports(
    driver_scores, year, round_number, circuit_key, profile, track_fit_by_team,
) -> list[dict[str, Any]]:
    """Aggregate driver scores into one team report per team."""
    by_team: dict[str, list[dict[str, Any]]] = {}
    for d in driver_scores:
        by_team.setdefault(d["team_code"], []).append(d)

    reports = []
    for team_code, drivers in by_team.items():
        drivers.sort(key=lambda d: d["predicted_position"])
        best = drivers[0]
        avg_combined = sum(d["score_breakdown"]["combined"] for d in drivers) / len(drivers)
        compat = compute_track_compatibility(
            _load_fingerprint(team_code, year, round_number - 1),
            profile,
        )
        reports.append({
            "team_code": team_code,
            "team": team_code,
            "race": f"Round {round_number}",
            "year": year,
            "round": round_number,
            "circuit": circuit_key,
            "track_compatibility": compat,
            "drivers": [
                {
                    "driver_code": d["driver_code"],
                    "driver_name": d.get("driver_name"),
                    "predicted_position": d["predicted_position"],
                    "qualifying_position": d.get("qualifying_position"),
                    "score": d["score_breakdown"]["combined"],
                    "signals": d["score_breakdown"]["signals"],
                    "weights": d["score_breakdown"]["weights"],
                    "input_data": d["input_data"],
                }
                for d in drivers
            ],
            "prediction": {
                "race": {
                    "predicted_position": best["predicted_position"],
                    "position_range": [
                        max(1, best["predicted_position"] - 1),
                        min(20, best["predicted_position"] + 2),
                    ],
                    "confidence": round(avg_combined / 100, 3),
                    "model_reasoning": (
                        f"Best driver {best['driver_code']} predicted P{best['predicted_position']} "
                        f"with combined score {best['score_breakdown']['combined']}/100."
                    ),
                },
                "dnf_probability": 0.08,
            },
            "score_breakdown": {
                "combined": round(avg_combined, 1),
                "historical_at_circuit": best["score_breakdown"]["signals"].get("historical") or 50,
                "recent_form": best["score_breakdown"]["signals"].get("recent_form") or 50,
                "track_fit": round(track_fit_by_team.get(team_code, 50), 1),
            },
        })

    reports.sort(key=lambda r: r["prediction"]["race"]["predicted_position"])
    return reports


# ---------------------- DynamoDB writes ----------------------

def _persist(year, round_number, driver_scores, team_reports):
    items = []
    for d in driver_scores:
        items.append(_to_ddb({
            "PK": f"PREDICTION#{year}#{round_number}",
            "SK": f"DRIVER#{d['driver_code']}",
            "DriverCode": d["driver_code"],
            "TeamCode": d["team_code"],
            "PredictedPosition": d["predicted_position"],
            "Combined": d["score_breakdown"]["combined"],
            "Signals": d["score_breakdown"]["signals"],
            "Weights": d["score_breakdown"]["weights"],
            "QualifyingPosition": d.get("qualifying_position"),
            "InputData": d["input_data"],
            "DriverName": d.get("driver_name"),
        }))
    for r in team_reports:
        items.append(_to_ddb({
            "PK": f"PREDICTION#{year}#{round_number}",
            "SK": f"TEAM#{r['team_code']}",
            "TeamCode": r["team_code"],
            "Report": r,
        }))
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    logger.info("persisted %d driver + %d team prediction items", len(driver_scores), len(team_reports))


def _to_ddb(obj):
    if isinstance(obj, dict):
        return {k: _to_ddb(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_to_ddb(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:
            return Decimal("0")
        return Decimal(str(round(obj, 6)))
    if isinstance(obj, bool):
        return obj
    return obj


def _next_round(year: int) -> int:
    response = table.scan(
        ProjectionExpression="PK",
        FilterExpression=Key("PK").begins_with(f"RACE#{year}#"),
    )
    rounds = set()
    for item in response.get("Items", []):
        try:
            rounds.add(int(item["PK"].split("#")[-1]))
        except ValueError:
            continue
    return (max(rounds) + 1) if rounds else 1
