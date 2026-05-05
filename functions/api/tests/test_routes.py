"""End-to-end router tests with DynamoDB mocked at the boto3.resource level."""
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
    """Patch the module-level DynamoDB table everywhere it's used."""
    table = MagicMock()
    with patch.object(_common, "table", table):
        yield table


def _api_event(path: str, method: str = "GET") -> dict:
    return {"path": path, "httpMethod": method, "requestContext": {}}


def test_unknown_route_returns_404(fake_table):
    response = api_app.handler(_api_event("/no/such/path"), None)
    assert response["statusCode"] == 404


def test_options_preflight_returns_204(fake_table):
    response = api_app.handler(_api_event("/races/2024", method="OPTIONS"), None)
    assert response["statusCode"] == 204
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_get_race_detail(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {"PK": "RACE#2024#5", "SK": "RESULT#VER", "Position": Decimal("1"), "Points": Decimal("26"), "DriverCode": "VER"},
            {"PK": "RACE#2024#5", "SK": "RESULT#NOR", "Position": Decimal("2"), "Points": Decimal("18"), "DriverCode": "NOR"},
            {"PK": "RACE#2024#5", "SK": "LAP#VER#001", "LapNumber": Decimal("1"), "LapTimeSeconds": Decimal("90.5"), "DriverCode": "VER"},
            {"PK": "RACE#2024#5", "SK": "TEAM_METRICS#RBR", "PointsScored": Decimal("26"), "TeamCode": "RBR"},
        ]
    }
    response = api_app.handler(_api_event("/races/2024/5"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["year"] == 2024
    assert body["round"] == 5
    assert body["results"][0]["DriverCode"] == "VER"
    assert body["results"][0]["Position"] == 1
    assert body["team_metrics"][0]["TeamCode"] == "RBR"


def test_get_race_detail_not_found(fake_table):
    fake_table.query.return_value = {"Items": []}
    response = api_app.handler(_api_event("/races/2030/1"), None)
    assert response["statusCode"] == 404


def test_get_standings(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {"PK": "STANDINGS#2024#10", "SK": "CONSTRUCTOR#RBR", "Position": Decimal("1"), "Points": Decimal("456")},
            {"PK": "STANDINGS#2024#10", "SK": "CONSTRUCTOR#MCL", "Position": Decimal("2"), "Points": Decimal("412")},
            {"PK": "STANDINGS#2024#10", "SK": "DRIVER#VER", "Position": Decimal("1"), "Points": Decimal("234")},
        ]
    }
    response = api_app.handler(_api_event("/standings/2024/10"), None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["constructors"][0]["SK"] == "CONSTRUCTOR#RBR"
    assert body["constructors"][0]["Position"] == 1
    assert body["drivers"][0]["SK"] == "DRIVER#VER"


def test_get_driver_profile(fake_table):
    fake_table.query.return_value = {
        "Items": [
            {"PK": "RACE#2024#1", "SK": "RESULT#VER", "Position": Decimal("1"), "Points": Decimal("26"), "DriverName": "Max Verstappen", "DriverCode": "VER", "TeamCode": "RBR"},
            {"PK": "RACE#2024#2", "SK": "RESULT#VER", "Position": Decimal("3"), "Points": Decimal("15"), "DriverCode": "VER", "TeamCode": "RBR"},
            {"PK": "RACE#2024#1", "SK": "LAP#VER#001", "DriverCode": "VER"},
        ]
    }
    response = api_app.handler(_api_event("/drivers/VER"), None)
    body = json.loads(response["body"])
    assert body["driver_code"] == "VER"
    assert body["wins"] == 1
    assert body["podiums"] == 2
    assert body["total_points"] == 41
    assert body["lap_count"] == 1


def test_response_includes_cors_headers(fake_table):
    fake_table.query.return_value = {"Items": [{"PK": "STANDINGS#2024#1", "SK": "CONSTRUCTOR#RBR", "Position": Decimal("1")}]}
    response = api_app.handler(_api_event("/standings/2024/1"), None)
    headers = response["headers"]
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in headers["Access-Control-Allow-Methods"]


def test_get_race_detail_via_rawpath_format(fake_table):
    """HTTP API v2 uses ``rawPath`` instead of ``path``."""
    fake_table.query.return_value = {
        "Items": [{"PK": "RACE#2024#5", "SK": "RESULT#VER", "Position": Decimal("1")}]
    }
    response = api_app.handler({"rawPath": "/races/2024/5", "requestContext": {"http": {"method": "GET"}}}, None)
    assert response["statusCode"] == 200
