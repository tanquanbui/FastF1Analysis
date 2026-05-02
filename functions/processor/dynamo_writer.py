"""Batched DynamoDB writer with type-coercion + dedup.

DynamoDB rejects ``float('nan')`` and Python floats — everything numeric goes
through ``Decimal`` first. Items are written via ``batch_writer`` (max 25 at a
time, retries unprocessed automatically).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

_dynamodb = boto3.resource(
    "dynamodb",
    config=Config(retries={"max_attempts": 5, "mode": "adaptive"}),
)


def batch_write(table_name: str, items: list[dict[str, Any]]) -> int:
    """Write a list of items to a table using batch_writer.

    Returns the count of items successfully submitted.
    """
    if not items:
        return 0

    table = _dynamodb.Table(table_name)
    written = 0
    with table.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
        for item in items:
            sanitised = _sanitise(item)
            if not sanitised.get("PK") or not sanitised.get("SK"):
                logger.warning("skipping item missing PK/SK: %s", sanitised)
                continue
            batch.put_item(Item=sanitised)
            written += 1

    logger.info("wrote %d items to %s", written, table_name)
    return written


def _sanitise(item: dict[str, Any]) -> dict[str, Any]:
    """Strip None values and convert floats to Decimal (DynamoDB requirement)."""
    out: dict[str, Any] = {}
    for key, value in item.items():
        if value is None:
            continue
        if isinstance(value, float):
            try:
                if value != value:  # NaN check
                    continue
                out[key] = Decimal(str(round(value, 6)))
            except (ValueError, ArithmeticError):
                continue
        elif isinstance(value, dict):
            sub = _sanitise(value)
            if sub:
                out[key] = sub
        elif isinstance(value, list):
            out[key] = [_sanitise_value(v) for v in value if v is not None]
        else:
            out[key] = value
    return out


def _sanitise_value(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(round(value, 6))) if value == value else Decimal("0")
    if isinstance(value, dict):
        return _sanitise(value)
    return value
