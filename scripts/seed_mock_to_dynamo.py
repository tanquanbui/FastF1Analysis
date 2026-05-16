"""One-shot: load every JSON fixture in scripts/mock_fixtures/ into DynamoDB."""
from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
TABLE_NAME = os.environ.get("TABLE_NAME", "F1Data")
FIXTURES = Path(__file__).parent / "mock_fixtures"


def _to_decimal(item):
    """DynamoDB rejects floats — convert recursively."""
    if isinstance(item, float):
        return Decimal(str(round(item, 6)))
    if isinstance(item, dict):
        return {k: _to_decimal(v) for k, v in item.items() if v is not None}
    if isinstance(item, list):
        return [_to_decimal(v) for v in item]
    return item


def main() -> int:
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    total = 0
    for fp in sorted(FIXTURES.glob("*.json")):
        with fp.open() as f:
            items = json.load(f)
        print(f"  {fp.name}: {len(items)} items")
        with table.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
            for item in items:
                batch.put_item(Item=_to_decimal(item))
        total += len(items)

    print(f"\nseeded {total} items into {TABLE_NAME} ({REGION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
