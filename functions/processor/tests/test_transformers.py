"""Tests for transformers — pure functions, no AWS dependencies."""
from __future__ import annotations

import pandas as pd
import pytest

import transformers


class TestNormaliseTeamCode:
    @pytest.mark.parametrize(
        "team, expected",
        [
            ("Red Bull Racing", "RBR"),
            ("red_bull", "RBR"),
            ("Red Bull", "RBR"),
            ("McLaren", "MCL"),
            ("Ferrari", "FER"),
            ("Mercedes", "MER"),
            ("Aston Martin", "AST"),
            ("aston_martin", "AST"),
            ("RB", "RB"),
            ("Racing Bulls", "RB"),
            ("Kick Sauber", "SAU"),
            ("Haas", "HAA"),
            ("Williams", "WIL"),
            ("", "UNK"),
        ],
    )
    def test_known_teams(self, team, expected):
        assert transformers.normalise_team_code(team) == expected

    def test_unknown_team_falls_back_to_uppercase_prefix(self):
        assert transformers.normalise_team_code("Unknown Team") == "UNK"


class TestCleanLapDataframe:
    def test_drops_pit_in_out_and_yellow_flag(self):
        df = pd.DataFrame(
            {
                "Driver": ["VER", "VER", "VER", "VER"],
                "Team": ["Red Bull"] * 4,
                "LapTime": pd.to_timedelta([90, 90, 95, 90], unit="s"),
                "LapNumber": [1, 2, 3, 4],
                "PitInTime": [pd.NaT, pd.NaT, pd.NaT, pd.Timestamp("2024-01-01")],
                "PitOutTime": [pd.NaT, pd.Timestamp("2024-01-01"), pd.NaT, pd.NaT],
                "TrackStatus": ["1", "1", "4", "1"],
            }
        )
        cleaned = transformers.clean_lap_dataframe(df)
        assert len(cleaned) == 1
        assert cleaned.iloc[0]["LapNumber"] == 1
        assert "LapTimeSeconds" in cleaned.columns
        assert cleaned.iloc[0]["LapTimeSeconds"] == 90.0

    def test_empty_input_returns_empty(self):
        assert transformers.clean_lap_dataframe(pd.DataFrame()).empty


class TestAggregateDriverLapSummary:
    def test_summary_per_driver(self):
        df = pd.DataFrame(
            {
                "Driver": ["VER", "VER", "VER", "NOR", "NOR"],
                "Team": ["Red Bull"] * 3 + ["McLaren"] * 2,
                "LapTimeSeconds": [90.0, 89.5, 91.0, 91.5, 91.8],
                "LapNumber": [1, 2, 3, 1, 2],
            }
        )
        summary = transformers.aggregate_driver_lap_summary(df)
        ver = next(s for s in summary if s["driver_code"] == "VER")
        nor = next(s for s in summary if s["driver_code"] == "NOR")

        assert ver["team_code"] == "RBR"
        assert ver["fastest_lap_s"] == 89.5
        assert ver["laps_completed"] == 3
        assert nor["team_code"] == "MCL"
        assert nor["fastest_lap_s"] == 91.5


class TestLapsToDynamoRecords:
    def test_keys_and_indexes_are_correct(self):
        df = pd.DataFrame(
            {
                "Driver": ["VER", "NOR"],
                "Team": ["Red Bull", "McLaren"],
                "LapTimeSeconds": [90.0, 91.0],
                "Sector1TimeSeconds": [28.0, 28.5],
                "Sector2TimeSeconds": [33.0, 33.5],
                "Sector3TimeSeconds": [29.0, 29.0],
                "LapNumber": [15, 15],
                "Position": [1, 2],
                "Stint": [1, 1],
                "Compound": ["MEDIUM", "HARD"],
                "TyreLife": [10, 12],
                "IsPersonalBest": [True, False],
                "TrackStatus": ["1", "1"],
                "SpeedI1": [310.0, 308.0],
                "SpeedI2": [None, 273.0],
                "SpeedFL": [298.0, 296.0],
                "SpeedST": [325.0, 322.0],
            }
        )
        items = transformers.laps_to_dynamo_records(df, 2024, 5)
        assert len(items) == 2
        ver = items[0]
        assert ver["PK"] == "RACE#2024#5"
        assert ver["SK"] == "LAP#VER#015"
        assert ver["DriverCode"] == "VER"
        assert ver["TeamCode"] == "RBR"
        assert ver["RaceKey"] == "2024#5"
        assert ver["LapTimeSeconds"] == 90.0
        assert ver["IsPersonalBest"] is True
        assert ver["SpeedI2"] is None  # NaN/None propagated correctly
        nor = items[1]
        assert nor["SpeedI2"] == 273.0


class TestResultsToDynamoRecords:
    def test_basic_conversion(self):
        results = [
            {
                "position": 1,
                "position_text": "1",
                "grid": 1,
                "laps": 57,
                "status": "Finished",
                "points": 26.0,
                "driver_code": "VER",
                "driver_id": "max_verstappen",
                "driver_name": "Max Verstappen",
                "constructor_id": "red_bull",
                "constructor_name": "Red Bull",
                "time_millis": 5400123,
                "fastest_lap_time": "1:32.123",
                "fastest_lap_rank": 1,
                "fastest_lap_speed_kph": 210.5,
            }
        ]
        items = transformers.results_to_dynamo_records(results, 2024, 5)
        assert items[0]["PK"] == "RACE#2024#5"
        assert items[0]["SK"] == "RESULT#VER"
        assert items[0]["TeamCode"] == "RBR"
        assert items[0]["Points"] == 26.0


class TestStandingsToDynamoRecords:
    def test_constructor_and_driver_both_emitted(self):
        constructor = [{"position": 1, "constructor_id": "red_bull", "constructor_name": "Red Bull", "points": 456.0, "wins": 10}]
        driver = [{"position": 1, "driver_code": "VER", "driver_name": "Max Verstappen", "points": 234.0, "wins": 7, "constructor_id": "red_bull"}]
        items = transformers.standings_to_dynamo_records(constructor, driver, 2024, 14)
        sks = {item["SK"] for item in items}
        assert sks == {"CONSTRUCTOR#RBR", "DRIVER#VER"}
        assert all(item["PK"] == "STANDINGS#2024#14" for item in items)
