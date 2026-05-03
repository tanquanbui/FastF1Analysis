"""Tests for dynamo_writer — float→Decimal coercion and dedup behaviour."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import dynamo_writer


@pytest.fixture
def fake_table():
    table = MagicMock()
    batch_ctx = MagicMock()
    batch_ctx.__enter__ = MagicMock(return_value=batch_ctx)
    batch_ctx.__exit__ = MagicMock(return_value=False)
    table.batch_writer.return_value = batch_ctx
    return table, batch_ctx


def test_floats_coerced_to_decimal(fake_table):
    table, batch_ctx = fake_table
    with patch.object(dynamo_writer, "_dynamodb") as ddb:
        ddb.Table.return_value = table
        dynamo_writer.batch_write(
            "F1Data",
            [{"PK": "RACE#2024#5", "SK": "RESULT#VER", "Points": 26.0, "LapTime": 89.567}],
        )

    item = batch_ctx.put_item.call_args.kwargs["Item"]
    assert item["Points"] == Decimal("26.0")
    assert item["LapTime"] == Decimal("89.567")


def test_none_values_stripped(fake_table):
    table, batch_ctx = fake_table
    with patch.object(dynamo_writer, "_dynamodb") as ddb:
        ddb.Table.return_value = table
        dynamo_writer.batch_write(
            "F1Data",
            [{"PK": "RACE#2024#5", "SK": "RESULT#VER", "Points": 26.0, "MissingField": None}],
        )

    item = batch_ctx.put_item.call_args.kwargs["Item"]
    assert "MissingField" not in item


def test_nan_values_stripped(fake_table):
    table, batch_ctx = fake_table
    nan = float("nan")
    with patch.object(dynamo_writer, "_dynamodb") as ddb:
        ddb.Table.return_value = table
        dynamo_writer.batch_write(
            "F1Data",
            [{"PK": "RACE#2024#5", "SK": "RESULT#VER", "Points": nan}],
        )

    item = batch_ctx.put_item.call_args.kwargs["Item"]
    assert "Points" not in item


def test_items_without_pk_skipped(fake_table):
    table, batch_ctx = fake_table
    with patch.object(dynamo_writer, "_dynamodb") as ddb:
        ddb.Table.return_value = table
        written = dynamo_writer.batch_write(
            "F1Data",
            [
                {"PK": "RACE#2024#5", "SK": "RESULT#VER", "Points": 26.0},
                {"PK": "RACE#2024#5", "Points": 18.0},
                {"SK": "RESULT#NOR", "Points": 18.0},
            ],
        )

    assert written == 1
    assert batch_ctx.put_item.call_count == 1


def test_empty_list_is_noop(fake_table):
    table, _ = fake_table
    with patch.object(dynamo_writer, "_dynamodb") as ddb:
        ddb.Table.return_value = table
        assert dynamo_writer.batch_write("F1Data", []) == 0
    ddb.Table.assert_not_called()


def test_nested_dict_sanitised(fake_table):
    table, batch_ctx = fake_table
    with patch.object(dynamo_writer, "_dynamodb") as ddb:
        ddb.Table.return_value = table
        dynamo_writer.batch_write(
            "F1Data",
            [{
                "PK": "RACE#2024#5",
                "SK": "TEAM_METRICS#RBR",
                "StatusSummary": {"Finished": 2, "Engine": 0},
                "BestLapSeconds": 89.5,
            }],
        )

    item = batch_ctx.put_item.call_args.kwargs["Item"]
    assert item["StatusSummary"] == {"Finished": 2, "Engine": 0}
    assert item["BestLapSeconds"] == Decimal("89.5")
