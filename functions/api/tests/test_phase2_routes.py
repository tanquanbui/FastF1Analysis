"""Tests for Phase 2 API routes: predictions, fingerprints, circuit, championship, upgrades."""
from __future__ import annotations

import json
import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

os.environ.setdefault("TABLE_NAME", "F1Data-test")

import pytest

import app as api_app
from routes import _common


@pytest.fixture
def fake_table():
    table = MagicMock()
    with patch.object(_common, "table", table):
        yield table


def _event(path: str, method: str = "GET") -> dict:
    return {"path": path, "httpMethod": method, "requestContext": {}}


# ----- predictions -----

def test_get_predictions_returns_reports(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {
                "PK": "PREDICTION#2024#5",
                "SK": "TEAM#RBR",
                "TeamCode": "RBR",
                "Report": {
                    "team_code": "RBR",
                    "team": "Red Bull Racing",
                    "race": "Monaco",
                    "round": 5,
                    "prediction": {"race": {"predicted_position": 1}},
                },
            },
            {
                "PK": "PREDICTION#2024#5",
                "SK": "TEAM#MCL",
                "TeamCode": "MCL",
                "Report": {
                    "team_code": "MCL",
                    "team": "McLaren",
                    "race": "Monaco",
                    "round": 5,
                    "prediction": {"race": {"predicted_position": 3}},
                },
            },
        ]
    }
    response = api_app.handler(_event("/predictions/2024/5"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["year"] == 2024
    assert body["round"] == 5
    assert body["race_name"] == "Monaco"
    # Sorted by predicted position
    assert body["team_reports"][0]["team_code"] == "RBR"


def test_get_predictions_404_when_missing(fake_table):
    fake_table.query.return_value = {"Items": []}
    response = api_app.handler(_event("/predictions/2030/1"), None)
    assert response["statusCode"] == 404


# ----- fingerprints -----

def test_get_team_fingerprint(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {
                "PK": "FINGERPRINT#2024#RBR",
                "SK": "TRACK#round_01",
                "Round": Decimal("1"),
                "straight_line_speed": Decimal("82"),
                "high_speed_cornering": Decimal("85"),
                "low_speed_cornering": Decimal("70"),
                "tyre_management": Decimal("80"),
                "qualifying_pace": Decimal("88"),
                "race_pace_conversion": Decimal("75"),
                "tyre_strategy_execution": Decimal("70"),
                "wet_weather_performance": Decimal("65"),
            },
            {
                "PK": "FINGERPRINT#2024#RBR",
                "SK": "TRACK#round_05",
                "Round": Decimal("5"),
                "straight_line_speed": Decimal("84"),
                "high_speed_cornering": Decimal("88"),
                "low_speed_cornering": Decimal("72"),
                "tyre_management": Decimal("82"),
                "qualifying_pace": Decimal("90"),
                "race_pace_conversion": Decimal("78"),
                "tyre_strategy_execution": Decimal("72"),
                "wet_weather_performance": Decimal("65"),
            },
        ]
    }
    response = api_app.handler(_event("/team/RBR/fingerprint"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["team_code"] == "RBR"
    assert body["latest_round"] == 5
    assert body["dimensions"]["high_speed_cornering"] == 88
    assert len(body["history"]) == 2


# ----- championship -----

def test_get_championship_scenarios(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {
                "PK": "SEASON_SIM#2024",
                "SK": "ROUND#10",
                "Round": Decimal("10"),
                "MonteCarlo": {
                    "title_probabilities": {"VER": Decimal("0.62"), "NOR": Decimal("0.30")},
                    "simulations": 10000,
                },
            }
        ]
    }
    response = api_app.handler(_event("/championship/2024/scenarios"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["as_of_round"] == 10
    assert body["title_probabilities"]["VER"] == 0.62


# ----- upgrades -----

def test_get_upgrades(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {
                "PK": "UPGRADE#2024#RBR",
                "SK": "RACE#08",
                "Round": Decimal("8"),
                "AffectedDimensions": ["high_speed_cornering", "qualifying_pace"],
                "Delta": {"high_speed_cornering": Decimal("4.2"), "qualifying_pace": Decimal("3.1")},
                "Confidence": Decimal("0.82"),
                "Notes": "Floor revision.",
            }
        ]
    }
    response = api_app.handler(_event("/upgrades/2024/RBR"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["events"][0]["round"] == 8
    assert body["events"][0]["delta"]["high_speed_cornering"] == 4.2
    assert "high_speed_cornering" in body["events"][0]["affected_dimensions"]
