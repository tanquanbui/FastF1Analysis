"""Integration tests for the ingestion handler with mocked AWS + clients."""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

os.environ.setdefault("RAW_BUCKET", "test-bucket")
os.environ.setdefault("ERGAST_BASE_URL", "https://example.invalid/ergast/f1")

import app


@pytest.fixture
def fake_laps():
    return pd.DataFrame(
        {
            "Driver": ["VER", "NOR"],
            "Team": ["Red Bull", "McLaren"],
            "LapTime": [pd.Timedelta(seconds=90), pd.Timedelta(seconds=91)],
            "LapNumber": [1, 1],
            "Position": [1, 2],
        }
    )


def test_handler_explicit_year_round(fake_laps):
    s3_mock = MagicMock()
    event = {"year": 2024, "round": 5, "session_types": ["R"]}

    with patch.object(app, "s3", s3_mock), \
         patch.object(app, "get_session_laps", return_value=fake_laps), \
         patch.object(app, "get_speed_trap_data", return_value=pd.DataFrame()), \
         patch.object(app, "get_weather_summary", return_value={"is_wet": False, "samples": 0}), \
         patch.object(app, "get_race_results", return_value=[]), \
         patch.object(app, "get_qualifying_results", return_value=[]), \
         patch.object(app, "get_pit_stop_data", return_value=[]), \
         patch.object(app, "get_constructor_standings", return_value=[]), \
         patch.object(app, "get_driver_standings", return_value=[]):
        result = app.handler(event, MagicMock())

    assert result["statusCode"] == 200
    assert result["body"]["year"] == 2024
    assert result["body"]["round"] == 5
    keys = [c.kwargs["Key"] for c in s3_mock.put_object.call_args_list]
    assert any("laps_R" in k for k in keys)
    assert any("_manifest.json" in k for k in keys)
    assert any("ergast.json" in k for k in keys)


def test_handler_skips_empty_session():
    s3_mock = MagicMock()
    event = {"year": 2024, "round": 5, "session_types": ["R"]}

    with patch.object(app, "s3", s3_mock), \
         patch.object(app, "get_session_laps", return_value=pd.DataFrame()), \
         patch.object(app, "get_speed_trap_data", return_value=pd.DataFrame()), \
         patch.object(app, "get_weather_summary", return_value={"is_wet": False, "samples": 0}), \
         patch.object(app, "get_race_results", return_value=[]), \
         patch.object(app, "get_qualifying_results", return_value=[]), \
         patch.object(app, "get_pit_stop_data", return_value=[]), \
         patch.object(app, "get_constructor_standings", return_value=[]), \
         patch.object(app, "get_driver_standings", return_value=[]):
        result = app.handler(event, MagicMock())

    keys = [c.kwargs["Key"] for c in s3_mock.put_object.call_args_list]
    assert not any("laps_R.parquet" in k for k in keys)
    assert result["statusCode"] == 200


def test_resolve_target_race_uses_explicit_values():
    year, rnd = app._resolve_target_race({"year": 2023, "round": 22})
    assert (year, rnd) == (2023, 22)


def test_resolve_target_race_falls_back_to_prev_season():
    """If the current season has no past races, jump to last year's finale."""
    prev_schedule = [
        {"year": 2023, "round": 21, "date": "2023-11-19"},
        {"year": 2023, "round": 22, "date": "2023-11-26"},
    ]
    with patch.object(app, "get_race_schedule", side_effect=[[], prev_schedule]):
        year, rnd = app._resolve_target_race({})
    assert (year, rnd) == (2023, 22)


def test_manifest_is_last_object_written(fake_laps):
    """The processor's S3 trigger fires on the manifest — it must be last."""
    s3_mock = MagicMock()
    event = {"year": 2024, "round": 5, "session_types": ["R"]}

    with patch.object(app, "s3", s3_mock), \
         patch.object(app, "get_session_laps", return_value=fake_laps), \
         patch.object(app, "get_speed_trap_data", return_value=pd.DataFrame()), \
         patch.object(app, "get_weather_summary", return_value={"is_wet": False, "samples": 0}), \
         patch.object(app, "get_race_results", return_value=[]), \
         patch.object(app, "get_qualifying_results", return_value=[]), \
         patch.object(app, "get_pit_stop_data", return_value=[]), \
         patch.object(app, "get_constructor_standings", return_value=[]), \
         patch.object(app, "get_driver_standings", return_value=[]):
        app.handler(event, MagicMock())

    last_call = s3_mock.put_object.call_args_list[-1]
    assert last_call.kwargs["Key"].endswith("_manifest.json")
    manifest = json.loads(last_call.kwargs["Body"].decode())
    assert manifest["year"] == 2024
    assert manifest["round"] == 5
