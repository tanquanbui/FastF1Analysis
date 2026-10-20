"""A stand-in for the fastf1 package, built from synthetic data.

Frames use FastF1's real column names and dtypes (Timedelta lap/sector times,
string TrackStatus, NaT pit times) so the loader and analysis code run exactly
as they would against live timing.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

DRIVERS = [
    ("1", "VER", "Max Verstappen", "Red Bull Racing", 0.00),
    ("4", "NOR", "Lando Norris", "McLaren", 0.10),
    ("16", "LEC", "Charles Leclerc", "Ferrari", 0.18),
    ("81", "PIA", "Oscar Piastri", "McLaren", 0.22),
    ("63", "RUS", "George Russell", "Mercedes", 0.35),
    ("44", "HAM", "Lewis Hamilton", "Mercedes", 0.40),
]
BASE_LAP = 95.0
def TD(seconds):
    return pd.to_timedelta(float(seconds), unit="s")


def _laps(n_laps: int, *, race: bool, seed: int, pit_lap: int | None = None,
          sc_laps: tuple[int, ...] = ()) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for idx, (_num, code, _name, team, delta) in enumerate(DRIVERS):
        stint, tyre_life, compound = 1, 0, "MEDIUM"
        for lap in range(1, n_laps + 1):
            tyre_life += 1
            pit_in = pit_out = pd.NaT
            if pit_lap and lap == pit_lap + (idx % 2):
                pit_in = TD(seconds=lap * 100)
            if pit_lap and lap == pit_lap + (idx % 2) + 1:
                stint, tyre_life, compound = 2, 1, "HARD"
                pit_out = TD(seconds=lap * 100)
            secs = BASE_LAP + delta + 0.08 * tyre_life - 0.05 * lap + rng.normal(0, 0.08)
            if not pd.isna(pit_in) or not pd.isna(pit_out):
                secs += 11.0
            status = "4" if lap in sc_laps else "1"
            if status == "4":
                secs += 25
            s1 = secs * 0.31
            rows.append({
                "Driver": code, "Team": team, "LapNumber": float(lap), "LapTime": TD(seconds=secs),
                "Stint": float(stint), "Compound": compound, "TyreLife": float(tyre_life),
                "PitInTime": pit_in, "PitOutTime": pit_out,
                "Sector1Time": TD(seconds=s1), "Sector2Time": TD(seconds=secs * 0.38),
                "Sector3Time": TD(seconds=secs - s1 - secs * 0.38),
                "SpeedST": 320.0 - 2 * idx + rng.normal(0, 1), "TrackStatus": status, "Deleted": False,
                "Position": float(idx + 1 if not race else min(len(DRIVERS), idx + 1 + (1 if lap == 1 and idx == 2 else 0))),
            })
    return pd.DataFrame(rows)


def _results(kind: str) -> pd.DataFrame:
    rows = []
    for i, (num, code, name, team, delta) in enumerate(DRIVERS):
        row = {"DriverNumber": num, "Abbreviation": code, "FullName": name, "TeamName": team,
               "Position": float(i + 1), "GridPosition": float(i + 1), "Status": "Finished", "Points": 0.0,
               "Q1": pd.NaT, "Q2": pd.NaT, "Q3": pd.NaT}
        if kind == "Qualifying":
            row["Q1"] = TD(seconds=91.0 + delta)
            row["Q2"] = TD(seconds=90.6 + delta)
            row["Q3"] = TD(seconds=90.2 + delta) if i < 5 else pd.NaT
        if kind == "Race":
            row["GridPosition"] = 0.0 if code == "HAM" else float(i + 1)
            if code == "RUS":
                row["Status"], row["Position"] = "Engine", float(len(DRIVERS))
            elif i == len(DRIVERS) - 1:
                row["Position"] = float(len(DRIVERS) - 1)
        rows.append(row)
    return pd.DataFrame(rows)


def _weather(rain: bool) -> pd.DataFrame:
    return pd.DataFrame({"AirTemp": [24.0, 26.0], "TrackTemp": [38.0, 44.0], "Humidity": [50.0, 55.0],
                         "WindSpeed": [1.5, 2.5], "Rainfall": [False, rain]})


class FakeSession:
    def __init__(self, name: str, year: int):
        self.name = name
        is_race = name in ("Race", "Sprint")
        n = {"Race": 30, "Sprint": 12, "Qualifying": 8}.get(name, 20)
        self.laps = _laps(n, race=is_race, seed=hash((name, year)) % 1000,
                          pit_lap=15 if name == "Race" else (8 if name.startswith("Practice") else None),
                          sc_laps=(20, 21, 22) if name == "Race" else ())
        self.results = _results(name)
        self.weather_data = _weather(rain=name == "Race")
        self.race_control_messages = pd.DataFrame({"Message": [
            "CAR 16 (LEC) TIME 1:31.000 DELETED - TRACK LIMITS AT TURN 4 LAP 3",
            "FIA STEWARDS: 5 PLACE GRID PENALTY FOR CAR 44 (HAM) - GEARBOX CHANGE",
            "GREEN LIGHT - PIT EXIT OPEN",
        ]})

    def load(self, **_kwargs) -> None:
        pass


class FakeEvent(dict):
    def __init__(self, year: int, rnd: int, location: str):
        super().__init__(Location=location, EventName="Test Grand Prix", EventFormat="conventional",
                         RoundNumber=rnd, Session1="Practice 1", Session2="Practice 2", Session3="Practice 3",
                         Session4="Qualifying", Session5="Race")
        self.year = year

    def get_session(self, name: str) -> FakeSession:
        return FakeSession(name, self.year)


class FakeErgast:
    def get_driver_standings(self, season, round):  # noqa: A002 - mirrors fastf1 signature
        df = pd.DataFrame([{"position": i + 1, "points": 100 - 10 * i, "wins": 1 if i == 0 else 0,
                            "driverCode": code, "constructorNames": [team]}
                           for i, (_, code, _, team, _) in enumerate(DRIVERS)])
        return SimpleNamespace(content=[df])

    def get_constructor_standings(self, season, round):  # noqa: A002
        teams = list(dict.fromkeys(t for *_, t, _ in DRIVERS))
        df = pd.DataFrame([{"position": i + 1, "points": 200 - 20 * i, "wins": 0, "constructorName": t}
                           for i, t in enumerate(teams)])
        return SimpleNamespace(content=[df])

    def get_race_results(self, season, round):  # noqa: A002
        df = pd.DataFrame([{"position": i + 1, "driverCode": code, "status": "Finished"}
                           for i, (_, code, *_rest) in enumerate(DRIVERS)])
        return SimpleNamespace(content=[df])


def make_module(location: str = "Shanghai") -> SimpleNamespace:
    def get_event_schedule(year, include_testing=False):
        return pd.DataFrame([{"Location": location, "RoundNumber": 5, "EventName": "Test Grand Prix",
                              "Country": "Testland"}])

    return SimpleNamespace(
        get_event=lambda year, rnd: FakeEvent(year, rnd, location),
        get_event_schedule=get_event_schedule,
    )
