"""Unit tests for fastf1_client — FastF1's session loader is mocked."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import fastf1_client


@pytest.fixture(autouse=True)
def reset_cache_flag():
    """Each test starts with the cache 'unconfigured' so we can assert init."""
    fastf1_client._cache_enabled = False
    yield


@pytest.fixture
def fake_session_with_laps():
    session = MagicMock()
    laps_df = pd.DataFrame(
        {
            "Driver": ["VER", "NOR"],
            "DriverNumber": ["1", "4"],
            "Team": ["Red Bull", "McLaren"],
            "LapTime": [pd.Timedelta(seconds=90.5), pd.Timedelta(seconds=91.2)],
            "Sector1Time": [pd.Timedelta(seconds=28.1), pd.Timedelta(seconds=28.5)],
            "Sector2Time": [pd.Timedelta(seconds=33.2), pd.Timedelta(seconds=33.4)],
            "Sector3Time": [pd.Timedelta(seconds=29.2), pd.Timedelta(seconds=29.3)],
            "Compound": ["MEDIUM", "HARD"],
            "TyreLife": [10, 12],
            "LapNumber": [15, 15],
            "Position": [1, 2],
            "Stint": [1, 1],
            "IsPersonalBest": [True, False],
            "TrackStatus": ["1", "1"],
            "PitInTime": [pd.NaT, pd.NaT],
            "PitOutTime": [pd.NaT, pd.NaT],
            "SpeedI1": [310.0, 308.0],
            "SpeedI2": [275.0, 273.0],
            "SpeedFL": [298.0, 296.0],
            "SpeedST": [325.0, 322.0],
        }
    )
    session.laps = laps_df
    session.load = MagicMock()
    return session


class TestGetSessionLaps:
    def test_returns_normalised_dataframe(self, fake_session_with_laps):
        with patch.object(fastf1_client.fastf1, "get_session", return_value=fake_session_with_laps), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache") as cache_mock:
            df = fastf1_client.get_session_laps(2024, 5, "R")

        cache_mock.assert_called_once()
        assert not df.empty
        assert list(df["Driver"]) == ["VER", "NOR"]
        assert "SpeedST" in df.columns
        assert df.iloc[0]["Position"] == 1

    def test_cache_is_only_configured_once(self, fake_session_with_laps):
        with patch.object(fastf1_client.fastf1, "get_session", return_value=fake_session_with_laps), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache") as cache_mock:
            fastf1_client.get_session_laps(2024, 5, "R")
            fastf1_client.get_session_laps(2024, 6, "Q")
        assert cache_mock.call_count == 1

    def test_empty_laps_returns_empty_df(self):
        session = MagicMock()
        session.laps = pd.DataFrame()
        session.load = MagicMock()
        with patch.object(fastf1_client.fastf1, "get_session", return_value=session), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache"):
            df = fastf1_client.get_session_laps(2024, 99, "R")
        assert df.empty

    def test_rejects_unknown_session_type(self):
        with pytest.raises(ValueError, match="unknown session_type"):
            fastf1_client.get_session_laps(2024, 5, "XYZ")


class TestGetSpeedTrapData:
    def test_aggregates_max_per_driver(self, fake_session_with_laps):
        with patch.object(fastf1_client.fastf1, "get_session", return_value=fake_session_with_laps), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache"):
            df = fastf1_client.get_speed_trap_data(2024, 5)
        ver = df[df["Driver"] == "VER"].iloc[0]
        assert ver["MaxSpeedST"] == 325.0

    def test_returns_empty_when_no_laps(self):
        session = MagicMock()
        session.laps = pd.DataFrame()
        session.load = MagicMock()
        with patch.object(fastf1_client.fastf1, "get_session", return_value=session), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache"):
            df = fastf1_client.get_speed_trap_data(2024, 99)
        assert df.empty
        assert "MaxSpeedST" in df.columns


class TestGetWeatherSummary:
    def test_flags_wet_session(self):
        session = MagicMock()
        session.weather_data = pd.DataFrame(
            {
                "Rainfall": [True, True, True, False, False],
                "AirTemp": [18, 17, 17, 18, 19],
                "TrackTemp": [22, 22, 21, 23, 24],
                "Humidity": [85, 90, 92, 80, 75],
            }
        )
        session.load = MagicMock()
        with patch.object(fastf1_client.fastf1, "get_session", return_value=session), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache"):
            summary = fastf1_client.get_weather_summary(2024, 5)
        assert summary["is_wet"] is True
        assert summary["rainfall_fraction"] == pytest.approx(0.6)
        assert summary["samples"] == 5

    def test_dry_session(self):
        session = MagicMock()
        session.weather_data = pd.DataFrame(
            {
                "Rainfall": [False] * 10,
                "AirTemp": [25] * 10,
                "TrackTemp": [40] * 10,
                "Humidity": [40] * 10,
            }
        )
        session.load = MagicMock()
        with patch.object(fastf1_client.fastf1, "get_session", return_value=session), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache"):
            summary = fastf1_client.get_weather_summary(2024, 5)
        assert summary["is_wet"] is False
        assert summary["rainfall_fraction"] == 0.0

    def test_no_weather_data(self):
        session = MagicMock()
        session.weather_data = pd.DataFrame()
        session.load = MagicMock()
        with patch.object(fastf1_client.fastf1, "get_session", return_value=session), \
             patch.object(fastf1_client.fastf1.Cache, "enable_cache"):
            summary = fastf1_client.get_weather_summary(2024, 5)
        assert summary == {"is_wet": False, "samples": 0}
