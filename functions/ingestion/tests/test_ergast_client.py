"""Unit tests for ergast_client — all upstream calls mocked."""
from __future__ import annotations

from unittest.mock import patch

import pytest

import ergast_client


@pytest.fixture
def mock_get():
    with patch.object(ergast_client, "_get") as m:
        yield m


class TestGetRaceSchedule:
    def test_returns_normalised_calendar(self, mock_get):
        mock_get.return_value = {
            "RaceTable": {
                "Races": [
                    {
                        "season": "2024",
                        "round": "1",
                        "raceName": "Bahrain Grand Prix",
                        "Circuit": {
                            "circuitId": "bahrain",
                            "circuitName": "Bahrain International Circuit",
                            "Location": {"country": "Bahrain", "locality": "Sakhir"},
                        },
                        "date": "2024-03-02",
                        "time": "15:00:00Z",
                    }
                ]
            }
        }

        races = ergast_client.get_race_schedule(2024)

        assert len(races) == 1
        assert races[0] == {
            "year": 2024,
            "round": 1,
            "name": "Bahrain Grand Prix",
            "circuit_id": "bahrain",
            "circuit_name": "Bahrain International Circuit",
            "country": "Bahrain",
            "locality": "Sakhir",
            "date": "2024-03-02",
            "time": "15:00:00Z",
        }

    def test_empty_calendar(self, mock_get):
        mock_get.return_value = {"RaceTable": {"Races": []}}
        assert ergast_client.get_race_schedule(2030) == []


class TestGetRaceResults:
    def test_normalises_finishing_driver(self, mock_get):
        mock_get.return_value = {
            "RaceTable": {
                "Races": [
                    {
                        "Results": [
                            {
                                "position": "1",
                                "positionText": "1",
                                "grid": "1",
                                "laps": "57",
                                "status": "Finished",
                                "points": "26",
                                "Driver": {
                                    "code": "VER",
                                    "driverId": "max_verstappen",
                                    "givenName": "Max",
                                    "familyName": "Verstappen",
                                },
                                "Constructor": {
                                    "constructorId": "red_bull",
                                    "name": "Red Bull",
                                },
                                "Time": {"millis": "5400123"},
                                "FastestLap": {
                                    "rank": "1",
                                    "Time": {"time": "1:32.123"},
                                    "AverageSpeed": {"speed": "210.5"},
                                },
                            }
                        ]
                    }
                ]
            }
        }

        results = ergast_client.get_race_results(2024, 1)

        assert len(results) == 1
        r = results[0]
        assert r["position"] == 1
        assert r["driver_code"] == "VER"
        assert r["constructor_id"] == "red_bull"
        assert r["points"] == 26.0
        assert r["time_millis"] == 5400123
        assert r["fastest_lap_rank"] == 1
        assert r["fastest_lap_speed_kph"] == 210.5

    def test_handles_dnf_with_non_numeric_position(self, mock_get):
        mock_get.return_value = {
            "RaceTable": {
                "Races": [
                    {
                        "Results": [
                            {
                                "position": "20",
                                "positionText": "R",
                                "grid": "10",
                                "laps": "30",
                                "status": "Engine",
                                "points": "0",
                                "Driver": {
                                    "code": "HAM",
                                    "driverId": "hamilton",
                                    "givenName": "Lewis",
                                    "familyName": "Hamilton",
                                },
                                "Constructor": {
                                    "constructorId": "mercedes",
                                    "name": "Mercedes",
                                },
                            }
                        ]
                    }
                ]
            }
        }

        r = ergast_client.get_race_results(2024, 5)[0]
        assert r["status"] == "Engine"
        assert r["time_millis"] is None
        assert r["fastest_lap_time"] is None

    def test_empty_when_no_race(self, mock_get):
        mock_get.return_value = {"RaceTable": {"Races": []}}
        assert ergast_client.get_race_results(2024, 99) == []


class TestStandings:
    def test_constructor_standings(self, mock_get):
        mock_get.return_value = {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "ConstructorStandings": [
                            {
                                "position": "1",
                                "points": "456",
                                "wins": "10",
                                "Constructor": {
                                    "constructorId": "red_bull",
                                    "name": "Red Bull",
                                    "nationality": "Austrian",
                                },
                            }
                        ]
                    }
                ]
            }
        }
        standings = ergast_client.get_constructor_standings(2024, 14)
        assert standings[0]["constructor_id"] == "red_bull"
        assert standings[0]["points"] == 456.0
        assert standings[0]["wins"] == 10

    def test_driver_standings(self, mock_get):
        mock_get.return_value = {
            "StandingsTable": {
                "StandingsLists": [
                    {
                        "DriverStandings": [
                            {
                                "position": "1",
                                "points": "234",
                                "wins": "7",
                                "Driver": {
                                    "code": "VER",
                                    "givenName": "Max",
                                    "familyName": "Verstappen",
                                },
                                "Constructors": [
                                    {"constructorId": "red_bull"}
                                ],
                            }
                        ]
                    }
                ]
            }
        }
        standings = ergast_client.get_driver_standings(2024, 14)
        assert standings[0]["driver_code"] == "VER"
        assert standings[0]["constructor_id"] == "red_bull"


class TestPitStops:
    def test_returns_typed_records(self, mock_get):
        mock_get.return_value = {
            "RaceTable": {
                "Races": [
                    {
                        "PitStops": [
                            {
                                "driverId": "max_verstappen",
                                "stop": "1",
                                "lap": "14",
                                "time": "15:43:12",
                                "duration": "23.456",
                            }
                        ]
                    }
                ]
            }
        }
        stops = ergast_client.get_pit_stop_data(2024, 5)
        assert stops == [
            {
                "driver_id": "max_verstappen",
                "stop": 1,
                "lap": 14,
                "time_of_day": "15:43:12",
                "duration_seconds": 23.456,
            }
        ]

    def test_handles_missing_duration(self, mock_get):
        mock_get.return_value = {
            "RaceTable": {
                "Races": [
                    {
                        "PitStops": [
                            {"driverId": "norris", "stop": "1", "lap": "10"}
                        ]
                    }
                ]
            }
        }
        stops = ergast_client.get_pit_stop_data(2024, 5)
        assert stops[0]["duration_seconds"] is None
        assert stops[0]["time_of_day"] is None
