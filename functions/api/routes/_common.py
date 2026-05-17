"""Shared helpers for route modules — DynamoDB resource + Decimal → JSON shim."""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]
table = _dynamodb.Table(TABLE_NAME)


def query_by_pk(pk: str, sk_prefix: str | None = None, limit: int = 5000) -> list[dict[str, Any]]:
    """Query DynamoDB by partition key; optionally filter SK by prefix.

    Paginates until the partition is exhausted or ``limit`` items are returned.
    Default limit is 5000 — large enough to fit a full race (results + ~1500
    laps + team metrics + standings would all live under one PK).
    """
    key_cond = Key("PK").eq(pk)
    if sk_prefix:
        key_cond = key_cond & Key("SK").begins_with(sk_prefix)
    items: list[dict[str, Any]] = []
    response = table.query(KeyConditionExpression=key_cond)
    items.extend(response.get("Items", []))
    while response.get("LastEvaluatedKey") and len(items) < limit:
        response = table.query(
            KeyConditionExpression=key_cond,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return [decimalify(item) for item in items[:limit]]


def query_index(index_name: str, partition_attr: str, partition_value: str, limit: int = 1000) -> list[dict[str, Any]]:
    response = table.query(
        IndexName=index_name,
        KeyConditionExpression=Key(partition_attr).eq(partition_value),
        Limit=limit,
    )
    return [decimalify(item) for item in response.get("Items", [])]


def decimalify(item: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert Decimal → int/float so json.dumps works."""
    out: dict[str, Any] = {}
    for key, value in item.items():
        out[key] = _convert(value)
    return out


def _convert(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_convert(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert(v) for k, v in value.items()}
    return value
