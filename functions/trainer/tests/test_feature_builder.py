"""Tests for the training feature builder."""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Make ml/ and shared layer importable for the builder.
ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "shared" / "python"))

import feature_builder


def _extract_pk_and_sk_prefix(cond):
    """Pull the partition key and the SK begins_with prefix out of a boto3
    KeyConditionExpression. Tightly coupled to how feature_builder builds the
    expression: ``Key('PK').eq(pk) & Key('SK').begins_with(sk_prefix)``.
    """
    pk = sk_prefix = None
    # `cond` is an And object whose ._values is (Equals, BeginsWith).
    if hasattr(cond, "_values") and len(cond._values) == 2:
        left, right = cond._values
        if hasattr(left, "get_expression"):
            pk = left.get_expression().get("values", [None, None])[1]
        if hasattr(right, "get_expression"):
            sk_prefix = right.get_expression().get("values", [None, None])[1]
    elif hasattr(cond, "get_expression"):
        # Single Eq (no SK filter)
        pk = cond.get_expression().get("values", [None, None])[1]
    return pk, sk_prefix


class _FakeTable:
    """In-memory DynamoDB substitute keyed by (PK, SK begins_with prefix)."""

    def __init__(self, items_by_pk, scan_items=None):
        # items_by_pk: {("RACE#2024#1", "RESULT#"): [item, ...]}
        self.items_by_pk = items_by_pk
        self.scan_items = scan_items or []

    def query(self, **kwargs):
        cond = kwargs.get("KeyConditionExpression")
        pk, sk_prefix = _extract_pk_and_sk_prefix(cond)
        for (key_pk, key_sk_prefix), items in self.items_by_pk.items():
            if key_pk != pk:
                continue
            if sk_prefix is None or key_sk_prefix == sk_prefix or sk_prefix.startswith(key_sk_prefix):
                return {"Items": items}
        return {"Items": []}

    def scan(self, **kwargs):
        return {"Items": self.scan_items}


def _result_item(driver: str, team: str, position: int, grid: int = 5):
    return {
        "DriverCode": driver,
        "TeamCode": team,
        "Position": Decimal(str(position)),
        "Grid": Decimal(str(grid)),
        "Points": Decimal(str(max(0, 26 - position * 2))),
    }


def _fingerprint_item(team: str, round_num: int):
    return {
        "PK": f"FINGERPRINT#2024#{team}",
        "SK": f"TRACK#round_{round_num:02d}",
        "TeamCode": team,
        "Round": Decimal(str(round_num)),
        "Year": Decimal("2024"),
        "straight_line_speed": Decimal("85"),
        "high_speed_cornering": Decimal("80"),
        "low_speed_cornering": Decimal("70"),
        "tyre_management": Decimal("75"),
        "qualifying_pace": Decimal("90"),
        "race_pace_conversion": Decimal("70"),
        "tyre_strategy_execution": Decimal("70"),
        "wet_weather_performance": Decimal("70"),
    }


def test_build_training_set_emits_rows():
    """Round 1 has results + fingerprint baseline at round 0 → builder yields rows."""
    table = _FakeTable(
        items_by_pk={
            ("RACE#2024#1", "RESULT#"): [
                _result_item("VER", "RBR", 1, 1),
                _result_item("NOR", "MCL", 2, 2),
            ],
        },
        scan_items=[_fingerprint_item("RBR", 0), _fingerprint_item("MCL", 0)],
    )
    builder = feature_builder.FeatureBuilder(table)
    rows, labels = builder.build_training_set([2024])

    assert len(rows) >= 2
    assert len(labels) == len(rows)
    assert all(0 <= l <= 4 for l in labels)


def test_to_csv_label_first_no_header():
    table = _FakeTable({})
    builder = feature_builder.FeatureBuilder(table)
    csv_text = builder.to_csv(rows=[[1.0, 2.0, 3.0]], labels=[2])
    assert csv_text.startswith("2,1.0,2.0,3.0")
    assert "\n" in csv_text  # csv.writer adds CRLF


def test_recent_form_handles_empty_history():
    table = _FakeTable({})
    builder = feature_builder.FeatureBuilder(table)
    form = builder._recent_form_for_driver("VER", 2024, 1)
    assert form["avg_finishing_position_l3"] == 10
    assert form["dnf_rate_l10"] == 0.0


def test_position_buckets_are_correct():
    """Spot-check: P1 → 0, P3 → 1, P5 → 2, P10 → 3, P20 → 4."""
    from features import position_to_bucket
    assert position_to_bucket(1) == 0
    assert position_to_bucket(3) == 1
    assert position_to_bucket(5) == 2
    assert position_to_bucket(10) == 3
    assert position_to_bucket(20) == 4
    assert position_to_bucket(None) == 4
