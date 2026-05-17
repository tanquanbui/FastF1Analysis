"""Fingerprint Lambda — invoked after the processor completes a race.

For every team in the race:
  1. Pull last N fingerprint records from DynamoDB.
  2. Compute the new fingerprint using the just-processed race features.
  3. Write the updated fingerprint to DynamoDB.
  4. Run the upgrade detector and persist any flagged event.

Event payload:
    {"year": 2024, "round": 5}
"""
from __future__ import annotations

import logging
import os
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from circuit_profiler import FINGERPRINT_DIMENSIONS
from feature_engineer import compute_team_fingerprint
from upgrade_detector import detect_upgrade_event

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

_dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]
table = _dynamodb.Table(TABLE_NAME)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point."""
    year = int(event["year"])
    round_number = int(event["round"])
    logger.info("computing fingerprints for %s round %s", year, round_number)

    # Find all teams that competed in this race via TEAM_METRICS records.
    team_metric_items = table.query(
        KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{round_number}") & Key("SK").begins_with("TEAM_METRICS#"),
    ).get("Items", [])

    teams = sorted({item.get("TeamCode") for item in team_metric_items if item.get("TeamCode")})
    if not teams:
        logger.warning("no team metrics for %s-%s", year, round_number)
        return {"statusCode": 200, "body": {"teams_processed": 0}}

    field_features = _gather_field_features_for_window(year, round_number)
    upgrade_events: list[dict[str, Any]] = []
    fingerprint_writes = 0

    for team_code in teams:
        history = _team_race_history(team_code, year, round_number)
        if not history:
            continue
        fingerprint = compute_team_fingerprint(team_code, history, field_features)
        _write_fingerprint(team_code, year, round_number, fingerprint)
        fingerprint_writes += 1

        # Upgrade detection — compare fingerprint series for this team
        series = _load_fingerprint_series(team_code, year)
        upgrade = detect_upgrade_event(team_code, round_number, series)
        if upgrade:
            _write_upgrade(team_code, year, upgrade)
            upgrade_events.append(upgrade)

    logger.info(
        "fingerprints updated=%s upgrades_detected=%s teams=%s",
        fingerprint_writes,
        len(upgrade_events),
        len(teams),
    )
    return {
        "statusCode": 200,
        "body": {
            "year": year,
            "round": round_number,
            "teams_processed": fingerprint_writes,
            "upgrade_events": upgrade_events,
        },
    }


def _team_race_history(team_code: str, year: int, round_number: int) -> list[dict[str, Any]]:
    """Walk this team's race-by-race aggregate metrics, oldest to newest, up
    to and including ``round_number``. Used to build the fingerprint input."""
    response = table.query(
        IndexName="TeamTrackIndex",
        KeyConditionExpression=Key("TeamCode").eq(team_code),
    )
    items = response.get("Items", [])
    history: list[dict[str, Any]] = []
    for item in items:
        sk = item.get("SK", "")
        if not sk.startswith("TEAM_METRICS#"):
            continue
        track_key = item.get("TrackKey") or ""
        if "#" not in track_key:
            continue
        item_year, item_round = track_key.split("#")
        if int(item_year) > year or (int(item_year) == year and int(item_round) > round_number):
            continue
        history.append(_team_metrics_to_features(item))
    history.sort(key=lambda h: (h["year"], h["race_round"]))
    return history


def _team_metrics_to_features(item: dict[str, Any]) -> dict[str, Any]:
    """Coerce a TEAM_METRICS item into the feature dict the fingerprint
    engineer expects.

    The processor's metrics module writes points, lap times, pit stops —
    enough to derive proxies for every dimension except wet weather (we
    don't track that yet). We expose each metric in its natural direction
    so the percentile_rank() in feature_engineer can do its job.
    """
    track_key = item.get("TrackKey") or ""
    year, rnd = track_key.split("#") if "#" in track_key else (None, None)

    def _f(key):
        v = item.get(key)
        return float(v) if v is not None else None

    best_lap = _f("BestLapSeconds")
    avg_pace = _f("AvgRacePaceSeconds")
    median_pace = _f("MedianRacePaceSeconds")
    pace_stddev = _f("LapPaceStdDev")
    pit_avg = _f("AvgPitDurationSeconds")
    points = _f("PointsScored") or 0.0
    drivers_finished = item.get("DriversFinished") or 0
    try:
        drivers_finished = int(drivers_finished)
    except (TypeError, ValueError):
        drivers_finished = 0

    return {
        "year": int(year) if year else None,
        "race_round": int(rnd) if rnd else None,
        # 1. Straight-line speed proxy: faster best lap → higher score.
        #    (We negate so 'higher is better' matches the percentile direction.)
        "best_speed_st": -best_lap if best_lap is not None else None,
        # 2. High-speed cornering: faster avg race pace = better aero platform.
        "high_speed_sector_gap": avg_pace,  # lower better
        # 3. Low-speed cornering: median race pace (less skewed by safety car laps).
        "low_speed_sector_gap": median_pace,  # lower better
        # 4. Tyre management: lower lap-time variance = better tyre work.
        "tyre_deg_rate": pace_stddev,  # lower better
        # 5. Qualifying pace proxy: best single lap.
        "qualifying_gap_to_pole": best_lap,  # lower better
        # 6. Race pace conversion: how many points did we walk away with?
        "race_finish_delta_from_grid": points + drivers_finished * 2,  # higher better
        # 7. Strategy execution: faster average pit stop time.
        "pit_consistency": pit_avg,  # lower better
        # 8. Wet weather: no track-status data in team_metrics, default later.
        "wet_race": False,
        "wet_finishing_rank": None,
    }


def _gather_field_features_for_window(year: int, round_number: int) -> list[dict[str, Any]]:
    """Field-wide team metrics across all teams over the last 8 races. Used
    as the percentile baseline.
    """
    field: list[dict[str, Any]] = []
    for r in range(max(1, round_number - 7), round_number + 1):
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{r}") & Key("SK").begins_with("TEAM_METRICS#"),
        )
        for item in response.get("Items", []):
            field.append(_team_metrics_to_features(item))
    return field


def _load_fingerprint_series(team_code: str, year: int) -> list[dict[str, Any]]:
    """Return every fingerprint written for this team in this season,
    oldest to newest.
    """
    response = table.query(
        KeyConditionExpression=Key("PK").eq(f"FINGERPRINT#{year}#{team_code}"),
    )
    series: list[dict[str, Any]] = []
    for item in response.get("Items", []):
        sk = item.get("SK", "")
        if not sk.startswith("TRACK#"):
            continue
        series.append(
            {
                "race_round": int(item.get("Round", 0)),
                "dimensions": {dim: float(item.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS},
            }
        )
    series.sort(key=lambda f: f["race_round"])
    return series


def _write_fingerprint(team_code: str, year: int, round_number: int, fingerprint: dict[str, float]) -> None:
    from decimal import Decimal

    item = {
        "PK": f"FINGERPRINT#{year}#{team_code}",
        "SK": f"TRACK#round_{round_number:02d}",
        "TeamCode": team_code,
        "TrackKey": f"round_{round_number:02d}",
        "Round": round_number,
        "Year": year,
    }
    for dim, value in fingerprint.items():
        item[dim] = Decimal(str(round(value, 2)))
    table.put_item(Item=item)
    logger.info("wrote fingerprint %s round %s", team_code, round_number)


def _write_upgrade(team_code: str, year: int, upgrade: dict[str, Any]) -> None:
    from decimal import Decimal

    item = {
        "PK": f"UPGRADE#{year}#{team_code}",
        "SK": f"RACE#{upgrade['detected_at_race']:02d}",
        "TeamCode": team_code,
        "Round": upgrade["detected_at_race"],
        "AffectedDimensions": upgrade["affected_dimensions"],
        "Confidence": Decimal(str(upgrade["confidence"])),
        "Notes": upgrade.get("notes", ""),
        "Delta": {dim: Decimal(str(d)) for dim, d in upgrade.get("delta", {}).items()},
    }
    table.put_item(Item=item)
    logger.info("wrote upgrade event for %s at round %s", team_code, upgrade["detected_at_race"])
