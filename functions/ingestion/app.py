"""Ingestion Lambda — pulls one race weekend's data from FastF1 + Ergast,
writes raw Parquet files to the raw S3 bucket.

Event payload (all fields optional — defaults to most recent past race):

    {
      "year": 2024,
      "round": 5,
      "session_types": ["R", "Q"]   // default ["R", "Q"]
    }

When invoked by the Monday-morning EventBridge schedule the event is fixed
(`{"source": "scheduled", "session_types": [...]}`) and we resolve the race
that was held on the previous Sunday via the Ergast calendar.
"""
from __future__ import annotations

import io
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import boto3
import pandas as pd

from ergast_client import (
    ErgastError,
    get_constructor_standings,
    get_driver_standings,
    get_pit_stop_data,
    get_qualifying_results,
    get_race_results,
    get_race_schedule,
)
from fastf1_client import get_session_laps, get_speed_trap_data, get_weather_summary

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
RAW_BUCKET = os.environ["RAW_BUCKET"]
DEFAULT_SESSIONS = ["R", "Q"]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point."""
    try:
        year, round_number = _resolve_target_race(event)
        session_types = event.get("session_types") or DEFAULT_SESSIONS
        logger.info("ingesting %s-%s sessions=%s", year, round_number, session_types)

        manifest = {
            "year": year,
            "round": round_number,
            "session_types": session_types,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "objects": [],
        }

        # FastF1 telemetry-style data
        for st in session_types:
            try:
                laps = get_session_laps(year, round_number, st)
            except Exception:
                logger.exception("FastF1 lap load failed for %s-%s %s", year, round_number, st)
                continue
            if laps.empty:
                logger.warning("no laps for %s-%s %s", year, round_number, st)
                continue
            key = _write_parquet(laps, f"races/{year}/{round_number}/laps_{st}.parquet")
            manifest["objects"].append(key)

        try:
            speeds = get_speed_trap_data(year, round_number)
            if not speeds.empty:
                manifest["objects"].append(
                    _write_parquet(speeds, f"races/{year}/{round_number}/speed_trap.parquet")
                )
        except Exception:
            logger.exception("speed-trap aggregation failed")

        try:
            weather = get_weather_summary(year, round_number)
            manifest["weather"] = weather
        except Exception:
            logger.exception("weather summary failed")

        # Ergast structured data — REST, retried internally
        try:
            ergast_payload = {
                "race_results": get_race_results(year, round_number),
                "qualifying_results": get_qualifying_results(year, round_number),
                "pit_stops": get_pit_stop_data(year, round_number),
                "constructor_standings": get_constructor_standings(year, round_number),
                "driver_standings": get_driver_standings(year, round_number),
            }
            manifest["objects"].append(
                _write_json(ergast_payload, f"races/{year}/{round_number}/ergast.json")
            )
        except ErgastError:
            logger.exception("Ergast mirror unavailable")

        # Manifest goes last so S3 event triggers the processor exactly once.
        manifest_key = f"races/{year}/{round_number}/_manifest.json"
        _write_json(manifest, manifest_key)
        logger.info("ingestion complete year=%s round=%s manifest=%s", year, round_number, manifest_key)

        return {
            "statusCode": 200,
            "body": {"year": year, "round": round_number, "manifest_key": manifest_key},
        }
    except Exception:
        logger.exception("ingestion failed")
        raise


def _resolve_target_race(event: dict[str, Any]) -> tuple[int, int]:
    """Pick the year/round to ingest.

    Priority:
      1. Explicit ``year`` + ``round`` in the event.
      2. Look up the most recent race whose date is ``<= today``.
    """
    if "year" in event and "round" in event:
        return int(event["year"]), int(event["round"])

    year = int(event.get("year") or date.today().year)
    schedule = get_race_schedule(year)
    today = date.today()
    past = (
        [r for r in schedule if datetime.strptime(r["date"], "%Y-%m-%d").date() <= today]
        if schedule
        else []
    )
    if not past:
        # Either the calendar isn't published yet or the season hasn't started.
        # Fall back to the previous year's final round.
        prev_schedule = get_race_schedule(year - 1)
        if not prev_schedule:
            raise RuntimeError(f"no races yet in {year} and no fallback in {year - 1}")
        last = prev_schedule[-1]
        return last["year"], last["round"]

    last_held = max(past, key=lambda r: r["round"])
    # Ingest the Monday after race day; if event runs Sunday night skip ahead by one
    # day so FastF1 has finished publishing the session payload.
    race_date = datetime.strptime(last_held["date"], "%Y-%m-%d").date()
    if today - race_date > timedelta(days=14):
        logger.warning("most recent race %s-%s is >14 days old", last_held["year"], last_held["round"])
    return last_held["year"], last_held["round"]


def _write_parquet(df: pd.DataFrame, key: str) -> str:
    """Serialise a DataFrame to Parquet and upload to S3. Returns the S3 key."""
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3.put_object(Bucket=RAW_BUCKET, Key=key, Body=buf.getvalue(), ContentType="application/octet-stream")
    logger.info("wrote s3://%s/%s (%d rows)", RAW_BUCKET, key, len(df))
    return key


def _write_json(payload: Any, key: str) -> str:
    """Write a JSON document to S3. Returns the S3 key."""
    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    s3.put_object(Bucket=RAW_BUCKET, Key=key, Body=body, ContentType="application/json")
    logger.info("wrote s3://%s/%s", RAW_BUCKET, key)
    return key
