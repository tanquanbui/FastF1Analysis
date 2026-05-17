"""Processor Lambda — triggered by S3 ``Object Created`` event on the
``_manifest.json`` key written by the ingestion Lambda.

Reads the raw parquet/json files for the race, computes per-lap and per-team
metrics, and writes structured records to DynamoDB. Also writes a slimmed
processed Parquet to the processed bucket for the historical backfill.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from typing import Any

import boto3
import pandas as pd

from dynamo_writer import batch_write
from metrics import (
    compute_driver_race_metrics,
    compute_team_race_metrics,
)
from transformers import (
    aggregate_driver_lap_summary,
    clean_lap_dataframe,
    laps_to_dynamo_records,
    qualifying_to_dynamo_records,
    results_to_dynamo_records,
    standings_to_dynamo_records,
)

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

s3 = boto3.client("s3")
RAW_BUCKET = os.environ["RAW_BUCKET"]
PROCESSED_BUCKET = os.environ["PROCESSED_BUCKET"]
TABLE_NAME = os.environ["TABLE_NAME"]

# Manifest path pattern: races/{year}/{round}/_manifest.json
MANIFEST_RE = re.compile(r"^races/(\d{4})/(\d{1,2})/_manifest\.json$")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point — EventBridge S3 Object Created event."""
    try:
        bucket, key = _extract_object(event)
        match = MANIFEST_RE.match(key)
        if not match:
            logger.info("ignoring non-manifest object %s", key)
            return {"statusCode": 200, "body": {"skipped": key}}

        year, round_number = int(match.group(1)), int(match.group(2))
        logger.info("processing race %s round %s from s3://%s/%s", year, round_number, bucket, key)

        manifest = _read_json(bucket, key)
        ergast_key = f"races/{year}/{round_number}/ergast.json"
        ergast = _read_json_if_exists(bucket, ergast_key) or {}

        laps_dfs: list[pd.DataFrame] = []
        for obj_key in manifest.get("objects", []):
            if not obj_key.endswith(".parquet") or "laps_" not in obj_key:
                continue
            laps_dfs.append(_read_parquet(bucket, obj_key))

        if laps_dfs:
            laps = pd.concat(laps_dfs, ignore_index=True)
            laps = clean_lap_dataframe(laps)
        else:
            laps = pd.DataFrame()

        results = ergast.get("race_results", [])
        qualifying = ergast.get("qualifying_results", [])
        pit_stops = ergast.get("pit_stops", [])
        constructor_standings = ergast.get("constructor_standings", [])
        driver_standings = ergast.get("driver_standings", [])
        weather = manifest.get("weather")

        # Build DynamoDB items
        lap_items = laps_to_dynamo_records(laps, year, round_number)
        result_items = results_to_dynamo_records(results, year, round_number)
        qualifying_items = qualifying_to_dynamo_records(qualifying, year, round_number)
        standings_items = standings_to_dynamo_records(
            constructor_standings, driver_standings, year, round_number
        )
        team_metric_items = compute_team_race_metrics(
            laps, results, pit_stops, year, round_number, weather=weather,
        )
        driver_metric_items = compute_driver_race_metrics(
            results, qualifying, year, round_number,
        )

        total_written = 0
        for batch in (
            result_items,
            lap_items,
            team_metric_items,
            driver_metric_items,
            standings_items,
            qualifying_items,
        ):
            total_written += batch_write(TABLE_NAME, batch)

        # Write a slimmed driver summary as processed parquet
        driver_summary = aggregate_driver_lap_summary(laps)
        if driver_summary:
            summary_df = pd.DataFrame(driver_summary)
            _write_processed_parquet(summary_df, f"races/{year}/{round_number}/driver_summary.parquet")

        logger.info(
            "processed %s-%s laps=%d results=%d standings=%d team_metrics=%d total_items=%d",
            year,
            round_number,
            len(lap_items),
            len(result_items),
            len(standings_items),
            len(team_metric_items),
            total_written,
        )
        return {
            "statusCode": 200,
            "body": {
                "year": year,
                "round": round_number,
                "items_written": total_written,
            },
        }
    except Exception:
        logger.exception("processor failed")
        raise


def _extract_object(event: dict[str, Any]) -> tuple[str, str]:
    """Pull bucket + key from EventBridge S3 event."""
    detail = event.get("detail", {})
    bucket = detail.get("bucket", {}).get("name")
    key = detail.get("object", {}).get("key")
    if not bucket or not key:
        raise ValueError(f"missing bucket/key in event: {event}")
    return bucket, key


def _read_json(bucket: str, key: str) -> dict[str, Any]:
    response = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read())


def _read_json_if_exists(bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return _read_json(bucket, key)
    except s3.exceptions.NoSuchKey:
        logger.info("optional object missing: s3://%s/%s", bucket, key)
        return None
    except Exception as exc:
        # boto3 raises ClientError 404 for missing objects; treat as soft-miss.
        if "NoSuchKey" in str(exc) or "404" in str(exc):
            return None
        raise


def _read_parquet(bucket: str, key: str) -> pd.DataFrame:
    response = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(response["Body"].read()))


def _write_processed_parquet(df: pd.DataFrame, key: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=key, Body=buf.getvalue())
    logger.info("wrote s3://%s/%s", PROCESSED_BUCKET, key)
