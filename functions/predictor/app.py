"""Predictor Lambda — Thursday pre-race analysis.

For each team competing in the upcoming round:
  1. Read current fingerprint + last upgrade event from DynamoDB.
  2. Look up the circuit profile and compute compatibility.
  3. Build the feature row, run XGBoost inference for the bucket prediction.
  4. Compose the structured report via report_builder.
  5. Run the championship Monte Carlo once for the season-wide title probabilities.
  6. Persist reports + season scenarios to DynamoDB.
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
import numpy as np
from boto3.dynamodb.conditions import Key

# `features`, `circuit_profiler`, `upgrade_detector` come from the shared
# Lambda Layer mounted at /opt/python/. Local-only modules are at /var/task/.
sys.path.insert(0, str(Path(__file__).parent))

from championship_sim import simulate_championship  # noqa: E402
from circuit_profiler import (  # noqa: E402
    FINGERPRINT_DIMENSIONS,
    compute_track_compatibility,
    get_profile,
)
from features import TRAINING_FEATURES, build_feature_row  # noqa: E402
from model_loader import load_latest_model  # noqa: E402
from report_builder import build_team_race_report  # noqa: E402
from upgrade_detector import project_upgrade_impact  # noqa: E402

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]
MODELS_BUCKET = os.environ["MODELS_BUCKET"]
table = dynamodb.Table(TABLE_NAME)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point."""
    year = int(event.get("year") or date.today().year)
    round_number = int(event.get("round") or _next_round(year))
    circuit_key = event.get("circuit_key") or _circuit_for_round(round_number)

    profile = get_profile(circuit_key) or {dim: 0.5 for dim in FINGERPRINT_DIMENSIONS}
    logger.info("predicting %s round %s circuit=%s", year, round_number, circuit_key)

    try:
        model = load_latest_model(MODELS_BUCKET)
    except Exception:
        logger.warning("model unavailable — falling back to compatibility-only predictions", exc_info=True)
        model = None

    standings = _load_standings(year, round_number - 1)
    team_reports: list[dict[str, Any]] = []
    position_distributions: dict[str, dict[int, float]] = {}

    teams = sorted({s["TeamCode"] for s in standings["constructors"] if s.get("TeamCode")})
    for team_code in teams:
        fingerprint = _load_fingerprint(team_code, year, round_number - 1)
        compat = compute_track_compatibility(fingerprint, profile)
        last_upgrade = _load_last_upgrade(team_code, year, round_number)
        upgrade_impact = project_upgrade_impact(last_upgrade, profile) if last_upgrade else None

        team_standings_row = next(
            (s for s in standings["constructors"] if s["TeamCode"] == team_code),
            None,
        )
        championship_position = int(team_standings_row["Position"]) if team_standings_row else 10
        championship_points_gap = _points_gap(standings["constructors"], team_code)

        feature_row = build_feature_row(
            team_fingerprint=fingerprint,
            circuit_profile=profile,
            track_compatibility=compat["overall_score"],
            recent_form={"avg_finishing_position_l3": 5, "avg_qualifying_position_l3": 5, "dnf_rate_l10": 0.05},
            championship_ctx={
                "position": championship_position,
                "points_gap_to_leader": championship_points_gap,
                "races_remaining": 24 - round_number,
                "must_win_pressure": 1 if championship_position == 2 and championship_points_gap > 25 else 0,
            },
            upgrade_ctx={
                "races_since_last_upgrade": (round_number - (last_upgrade or {}).get("detected_at_race", -50)) if last_upgrade else 99,
                "upgrade_dimension_delta_max": max(((last_upgrade or {}).get("delta") or {}).values(), default=0),
            },
            session_ctx={"practice_pace_rank": championship_position, "qualifying_position": championship_position},
            weather_ctx={"rain_probability": 0.1, "expected_temperature": 25.0},
        )

        prediction = _model_predict(model, feature_row)
        position_distributions.update(_distribution_from_bucket(prediction["bracket"], team_code, standings))

        report = build_team_race_report(
            team_code=team_code,
            team_name=team_code,
            upcoming_race={"name": f"Round {round_number}", "round": round_number, "year": year},
            current_fingerprint=fingerprint,
            compatibility=compat,
            last_upgrade=last_upgrade,
            upgrade_impact=upgrade_impact,
            championship_position=championship_position,
            championship_points_gap=championship_points_gap,
            races_remaining=24 - round_number,
            model_prediction=prediction,
        )
        team_reports.append(report)

    # Season-wide Monte Carlo runs once per invocation.
    drivers = [
        {"driver_code": d["DriverCode"], "team_code": d.get("TeamCode"), "points": float(d.get("Points") or 0)}
        for d in standings["drivers"]
    ]
    constructors_in = [
        {"team_code": c["TeamCode"], "points": float(c.get("Points") or 0)}
        for c in standings["constructors"]
    ]
    monte_carlo = simulate_championship(
        current_standings={"drivers": drivers, "constructors": constructors_in},
        remaining_races=[{"name": f"round_{r}"} for r in range(round_number, 25)],
        position_distributions=_driver_position_distributions(drivers, position_distributions),
        n_simulations=int(event.get("simulations", 5000)),
    )

    _persist_predictions(year, round_number, team_reports, monte_carlo)
    return {
        "statusCode": 200,
        "body": {
            "year": year,
            "round": round_number,
            "circuit": circuit_key,
            "team_reports_count": len(team_reports),
            "title_probabilities": monte_carlo.get("title_probabilities", {}),
        },
    }


# ----- helpers -----

def _next_round(year: int) -> int:
    """Find the smallest round > the most recent ingested race."""
    response = table.scan(
        ProjectionExpression="PK, SK",
        FilterExpression=Key("PK").begins_with(f"RACE#{year}#"),
    )
    rounds = set()
    for item in response.get("Items", []):
        try:
            rounds.add(int(item["PK"].split("#")[-1]))
        except ValueError:
            continue
    return (max(rounds) + 1) if rounds else 1


def _circuit_for_round(round_number: int) -> str:
    from feature_builder import CALENDAR_CIRCUITS_2024  # type: ignore
    return CALENDAR_CIRCUITS_2024.get(round_number, "monza")


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


def _load_last_upgrade(team_code: str, year: int, before_round: int) -> dict[str, Any] | None:
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"UPGRADE#{year}#{team_code}"),
    )
    items = [i for i in response.get("Items", []) if int(i.get("Round") or 0) < before_round]
    if not items:
        return None
    items.sort(key=lambda i: int(i.get("Round")), reverse=True)
    top = items[0]
    return {
        "detected_at_race": int(top.get("Round")),
        "affected_dimensions": list(top.get("AffectedDimensions") or []),
        "confidence": float(top.get("Confidence") or 0.5),
        "delta": {dim: float(d) for dim, d in (top.get("Delta") or {}).items()},
        "notes": top.get("Notes", ""),
    }


def _load_standings(year: int, round_number: int) -> dict[str, list[dict[str, Any]]]:
    if round_number <= 0:
        return {"drivers": [], "constructors": []}
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"STANDINGS#{year}#{round_number}"),
    )
    items = response.get("Items", [])
    return {
        "drivers": [i for i in items if i["SK"].startswith("DRIVER#")],
        "constructors": [i for i in items if i["SK"].startswith("CONSTRUCTOR#")],
    }


def _points_gap(constructors: list[dict[str, Any]], team_code: str) -> int:
    if not constructors:
        return 0
    sorted_const = sorted(constructors, key=lambda c: int(c.get("Position") or 99))
    leader_points = float(sorted_const[0].get("Points") or 0)
    own_points = next((float(c.get("Points") or 0) for c in constructors if c.get("TeamCode") == team_code), 0)
    return max(0, int(leader_points - own_points))


def _model_predict(model, feature_row: dict[str, float]) -> dict[str, Any]:
    """Run the model if available, otherwise fall back to a heuristic."""
    if model is None:
        # Heuristic: compatibility ≥ 65 → bracket 1; ≥ 50 → 2; ≥ 35 → 3; else 4.
        compat = feature_row["track_compatibility_score"]
        bracket = (
            0 if compat >= 75 else
            1 if compat >= 60 else
            2 if compat >= 45 else
            3 if compat >= 30 else 4
        )
        confidence = max(0.4, 1 - abs(compat - 50) / 100)
        return {"bracket": bracket, "confidence": confidence, "dnf_probability": 0.08}

    import numpy as np
    x = np.array([[feature_row[name] for name in TRAINING_FEATURES]], dtype=float)
    probabilities = model.predict_proba(x)[0]
    bracket = int(np.argmax(probabilities))
    confidence = float(probabilities[bracket])
    return {"bracket": bracket, "confidence": confidence, "dnf_probability": 0.08}


def _distribution_from_bucket(bracket: int, team_code: str, standings) -> dict[str, dict[int, float]]:
    """Translate a position bucket into an approximate per-position distribution.
    Used by the Monte Carlo simulator below.
    """
    bracket_to_dist = {
        0: {1: 0.55, 2: 0.20, 3: 0.10, 4: 0.07, 5: 0.04, 6: 0.02, 7: 0.01, 8: 0.005, 9: 0.005},
        1: {1: 0.15, 2: 0.30, 3: 0.25, 4: 0.12, 5: 0.08, 6: 0.04, 7: 0.03, 8: 0.02, 9: 0.01},
        2: {2: 0.05, 3: 0.10, 4: 0.20, 5: 0.20, 6: 0.18, 7: 0.10, 8: 0.07, 9: 0.05, 10: 0.05},
        3: {5: 0.08, 6: 0.12, 7: 0.15, 8: 0.18, 9: 0.15, 10: 0.12, 11: 0.10, 12: 0.05, 13: 0.05},
        4: {10: 0.05, 11: 0.08, 12: 0.10, 13: 0.15, 14: 0.18, 15: 0.18, 16: 0.12, 17: 0.08, 18: 0.04, 19: 0.02},
    }
    dist = bracket_to_dist.get(bracket, bracket_to_dist[3])
    # Both drivers in a team get the same distribution as a first approximation.
    drivers = [d for d in standings["drivers"] if d.get("TeamCode") == team_code]
    return {d["DriverCode"]: dist for d in drivers}


def _driver_position_distributions(drivers, partial):
    """Fill in any missing drivers with a flat distribution."""
    out = dict(partial)
    for d in drivers:
        code = d["driver_code"]
        if code not in out:
            out[code] = {p: 1 / 20 for p in range(1, 21)}
    return out


def _persist_predictions(year, round_number, reports, monte_carlo):
    """Write reports + season title-probabilities as DynamoDB items."""
    with table.batch_writer() as batch:
        for report in reports:
            batch.put_item(Item=_to_ddb_item({
                "PK": f"PREDICTION#{year}#{round_number}",
                "SK": f"TEAM#{report['team_code']}",
                "TeamCode": report["team_code"],
                "Report": report,
            }))
        batch.put_item(Item=_to_ddb_item({
            "PK": f"SEASON_SIM#{year}",
            "SK": f"ROUND#{round_number:02d}",
            "Round": round_number,
            "MonteCarlo": monte_carlo,
        }))
    logger.info("persisted %d reports + season sim", len(reports))


def _to_ddb_item(obj):
    """Recursively coerce floats → Decimal; strip None."""
    if isinstance(obj, dict):
        return {k: _to_ddb_item(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_to_ddb_item(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return Decimal("0")
        return Decimal(str(round(obj, 6)))
    return obj
