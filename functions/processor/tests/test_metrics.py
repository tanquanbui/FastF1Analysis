"""Tests for race-metric computation."""
from __future__ import annotations

import pandas as pd

import metrics


def _laps(*, drivers, teams, times, lap_numbers, compounds=None, tyre_life=None):
    df = pd.DataFrame(
        {
            "Driver": drivers,
            "Team": teams,
            "LapTimeSeconds": times,
            "LapNumber": lap_numbers,
        }
    )
    if compounds is not None:
        df["Compound"] = compounds
    if tyre_life is not None:
        df["TyreLife"] = tyre_life
    return df


class TestComputeTeamRaceMetrics:
    def test_aggregates_points_and_pace(self):
        results = [
            {"position": 1, "driver_code": "VER", "driver_id": "max_verstappen", "constructor_id": "red_bull", "points": 26.0, "status": "Finished"},
            {"position": 5, "driver_code": "PER", "driver_id": "perez", "constructor_id": "red_bull", "points": 10.0, "status": "Finished"},
            {"position": 2, "driver_code": "NOR", "driver_id": "norris", "constructor_id": "mclaren", "points": 18.0, "status": "Finished"},
        ]
        laps = _laps(
            drivers=["VER", "VER", "PER", "NOR"],
            teams=["Red Bull", "Red Bull", "Red Bull", "McLaren"],
            times=[90.0, 89.5, 91.0, 90.5],
            lap_numbers=[1, 2, 1, 1],
        )
        pit_stops = [
            {"driver_id": "max_verstappen", "duration_seconds": 22.0},
            {"driver_id": "perez", "duration_seconds": 23.5},
            {"driver_id": "norris", "duration_seconds": 21.5},
        ]
        items = metrics.compute_team_race_metrics(laps, results, pit_stops, 2024, 5)
        teams = {item["TeamCode"]: item for item in items}

        assert teams["RBR"]["PointsScored"] == 36.0
        assert teams["RBR"]["DriversFinished"] == 2
        assert teams["RBR"]["BestLapSeconds"] == 89.5
        assert teams["RBR"]["PitStopCount"] == 2
        assert teams["RBR"]["AvgPitDurationSeconds"] == 22.75
        assert teams["MCL"]["PointsScored"] == 18.0
        assert teams["MCL"]["PitStopCount"] == 1

    def test_handles_dnf_status(self):
        results = [
            {"position": 20, "driver_code": "HAM", "driver_id": "hamilton", "constructor_id": "mercedes", "points": 0.0, "status": "Engine"},
        ]
        items = metrics.compute_team_race_metrics(pd.DataFrame(), results, [], 2024, 5)
        mer = next(i for i in items if i["TeamCode"] == "MER")
        assert mer["DriversFinished"] == 0
        assert mer["StatusSummary"] == {"Engine": 1}

    def test_empty_inputs(self):
        assert metrics.compute_team_race_metrics(pd.DataFrame(), [], [], 2024, 5) == []


class TestComputeTyreDegradation:
    def test_positive_slope_when_laps_get_slower(self):
        laps = _laps(
            drivers=["VER"] * 8,
            teams=["Red Bull"] * 8,
            times=[90.0, 90.2, 90.5, 90.8, 91.1, 91.4, 91.7, 92.0],
            lap_numbers=list(range(1, 9)),
            compounds=["MEDIUM"] * 8,
            tyre_life=list(range(1, 9)),
        )
        deg = metrics.compute_tyre_degradation(laps)
        assert "VER" in deg
        assert "MEDIUM" in deg["VER"]
        assert deg["VER"]["MEDIUM"] > 0

    def test_skips_short_stints(self):
        laps = _laps(
            drivers=["VER"] * 3,
            teams=["Red Bull"] * 3,
            times=[90.0, 90.1, 90.2],
            lap_numbers=[1, 2, 3],
            compounds=["SOFT"] * 3,
            tyre_life=[1, 2, 3],
        )
        assert metrics.compute_tyre_degradation(laps) == {}

    def test_empty_input(self):
        assert metrics.compute_tyre_degradation(pd.DataFrame()) == {}


class TestComputeSectorRankings:
    def test_ranks_per_sector(self):
        df = pd.DataFrame(
            {
                "Driver": ["VER", "VER", "NOR", "NOR"],
                "Sector1TimeSeconds": [28.0, 28.2, 28.5, 28.3],
                "Sector2TimeSeconds": [33.5, 33.4, 33.0, 33.1],
                "Sector3TimeSeconds": [29.0, 28.8, 29.2, 29.1],
            }
        )
        rankings = metrics.compute_sector_rankings(df)
        assert rankings["VER"]["Sector1"] == 1
        assert rankings["NOR"]["Sector2"] == 1
        assert rankings["VER"]["Sector3"] == 1
