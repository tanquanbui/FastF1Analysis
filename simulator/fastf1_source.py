"""Build a full race context from FastF1.

Loads everything known *before the race starts*:

* every session of the weekend (practice, sprint qualifying / shootout, sprint,
  qualifying): pace, ideal laps, speed traps, long runs and tyre degradation
* qualifying results and the race grid (incl. penalties / pit-lane starts)
* weather per session, race-control penalties and track-limit deletions
* championship standings and recent results (Ergast via FastF1)
* the last few races at this circuit: strategies, safety cars, measured pit loss

The race result itself is loaded only to score simulations afterwards and is
never put in the prompt. Race-day weather *is* included by default as a
stand-in for a forecast; pass ``race_weather=False`` for a strict backtest.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable


from . import weekend as wk
from .circuits import CIRCUITS, circuit_for_round, circuit_key_for_location
from .context import ROOT, CircuitInfo, DataTable, DriverEntry, RaceContext, team_code

logger = logging.getLogger(__name__)

HISTORY_YEARS = 3
PRE_RACE_SESSIONS = ("Practice 1", "Practice 2", "Practice 3", "Sprint Shootout", "Sprint Qualifying",
                     "Sprint", "Qualifying")

Progress = Callable[[str], None]


def _fastf1():
    import fastf1

    cache = Path(os.environ.get("FASTF1_CACHE", ROOT / "fastf1_cache"))
    cache.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))
    return fastf1


def _load(event: Any, name: str, **kwargs: bool) -> Any | None:
    try:
        session = event.get_session(name)
        session.load(**{"laps": False, "telemetry": False, "weather": False, "messages": False, **kwargs})
        return session
    except Exception as exc:  # noqa: BLE001 - session missing for this format, or not run yet
        logger.info("skip %s: %s", name, exc)
        return None


def _session_names(event: Any) -> list[str]:
    names = [str(event.get(f"Session{i}", "")) for i in range(1, 6)]
    return [n for n in names if n in PRE_RACE_SESSIONS]


def from_fastf1(
    year: int,
    round_number: int,
    *,
    history_years: int = HISTORY_YEARS,
    race_weather: bool = True,
    progress: Progress | None = None,
) -> RaceContext:
    say = progress or (lambda msg: logger.info(msg))
    fastf1 = _fastf1()

    event = fastf1.get_event(year, round_number)
    key = circuit_key_for_location(str(event["Location"])) or circuit_for_round(year, round_number)
    if key is None or key not in CIRCUITS:
        raise ValueError(f"unknown circuit location {event['Location']!r}")
    circuit = CircuitInfo(key=key, **CIRCUITS[key])
    tables: list[DataTable] = []
    notes: list[str] = []
    drivers: dict[str, DriverEntry] = {}
    car_numbers: dict[str, str] = {}

    # ---- weekend sessions -------------------------------------------------
    pace_by_session: dict[str, dict[str, dict[str, Any]]] = {}
    all_runs: list[dict[str, Any]] = []
    weather_rows: list[list[Any]] = []
    penalties: list[str] = []
    seen_messages: set[str] = set()
    deletions: dict[str, int] = {}
    quali = sprint = None

    for name in _session_names(event):
        say(f"Loading {name}")
        session = _load(event, name, laps=True, weather=True, messages=True)
        if session is None:
            continue
        for _, r in session.results.iterrows():
            car_numbers[str(r["DriverNumber"])] = r["Abbreviation"]
            drivers.setdefault(
                r["Abbreviation"],
                DriverEntry(code=r["Abbreviation"], name=r.get("FullName"), team=team_code(r.get("TeamName"))),
            )
        laps = session.laps
        pace_by_session[name] = {row["driver"]: row for row in wk.session_pace(laps)}
        if name.startswith("Practice") or name == "Sprint":
            runs = wk.long_runs(laps)
            for r in runs:
                r["session"] = name
            all_runs.extend(runs)
        w = wk.weather_summary(session.weather_data)
        if w:
            weather_rows.append([name, w["air_c"], w["track_c"], w["humidity_pct"], w["wind_ms"], w["rain_share"]])
        for m in wk.race_control_highlights(session.race_control_messages):
            if m not in seen_messages:
                seen_messages.add(m)
                penalties.append(f"[{name}] {m}")
        for car, n in wk.track_limit_deletions(session.race_control_messages).items():
            deletions[car] = deletions.get(car, 0) + n
        if name == "Qualifying":
            quali = session
        elif name == "Sprint":
            sprint = session

    if not drivers:
        raise ValueError(f"FastF1 has no session data for {year} round {round_number} yet")

    # ---- qualifying & grid ------------------------------------------------
    if quali is not None:
        q_rows = wk.qualifying_table(quali.results)
        for r in q_rows:
            if r["driver"] in drivers:
                drivers[r["driver"]].grid = r["pos"]
                drivers[r["driver"]].quali_gap_s = r["gap_s"]
        tables.append(DataTable(
            key="qualifying", section="weekend", title="Qualifying",
            columns=["Pos", "Driver", "Team", "Q1", "Q2", "Q3", "Gap to pole (s)"],
            rows=[[r["pos"], r["driver"], team_code(r["team"]), r["q1"], r["q2"], r["q3"], r["gap_s"]] for r in q_rows],
        ))

    say("Loading race grid")
    race = _load(event, "Race", weather=race_weather)
    actual: list[str] | None = None
    if race is not None and len(race.results):
        for r in wk.classification(race.results):
            entry = drivers.get(r["driver"])
            if entry is None:
                continue
            if r["grid"] == 0:
                entry.grid = None
                entry.notes = "Starts from the pit lane"
            elif r["grid"]:
                entry.grid = r["grid"]  # official grid, after penalties
        finished = [r for r in wk.classification(race.results) if r["pos"]]
        actual = [r["driver"] for r in finished] or None

    # ---- pace tables ------------------------------------------------------
    sessions = list(pace_by_session)
    if sessions:
        rows = []
        for code in sorted(drivers, key=lambda c: (drivers[c].grid or 99, c)):
            row: list[Any] = [code, drivers[code].team]
            for s in sessions:
                p = pace_by_session[s].get(code)
                row.append(f"+{p['gap_s']:.3f}" if p and p["gap_s"] is not None else "-")
            speeds = [pace_by_session[s][code]["top_speed_kph"] for s in sessions
                      if code in pace_by_session[s] and pace_by_session[s][code]["top_speed_kph"]]
            ideal = pace_by_session.get("Qualifying", {}).get(code, {}).get("ideal_s")
            laps_run = sum(pace_by_session[s][code]["laps"] for s in sessions if code in pace_by_session[s])
            row += [max(speeds) if speeds else "-", ideal or "-", laps_run]
            rows.append(row)
        tables.append(DataTable(
            key="session_pace", section="weekend", title="One-lap pace by session (gap to session best)",
            columns=["Driver", "Team", *sessions, "Top speed (kph)", "Quali ideal lap (s)", "Laps run"],
            rows=rows,
            note="Practice gaps mix fuel loads and programmes; qualifying is the cleanest one-lap read.",
        ))

    if all_runs:
        best = wk.best_long_run(all_runs)
        for code, r in best.items():
            if code in drivers:
                drivers[code].long_run_pace_s = r["median_s"]
                drivers[code].long_run_compound = r["compound"]
        tables.append(DataTable(
            key="long_runs", section="weekend", title="Long runs (green-flag stints of 5+ laps)",
            columns=["Driver", "Team", "Session", "Compound", "Laps", "Median lap (s)", "Deg (s/lap, fuel-corrected)"],
            rows=[[r["driver"], team_code(r["team"]), r["session"], r["compound"], r["laps"], r["median_s"],
                   r["deg_s_per_lap"]] for r in _longest_per_compound(all_runs)],
            note=f"Each driver's longest run per compound. Deg = lap-time slope vs tyre age + "
                 f"{wk.FUEL_EFFECT_S_PER_LAP}s/lap fuel burn. Teams run different fuel loads, so compare "
                 "deg more than absolute pace.",
        ))
        tables.append(DataTable(
            key="compounds", section="weekend", title="Compound behaviour across the field",
            columns=["Compound", "Runs", "Median pace (s)", "Median deg (s/lap)", "80th pct deg", "Longest run"],
            rows=[[c["compound"], c["runs"], c["median_pace_s"], c["median_deg_s_per_lap"], c["high_deg_s_per_lap"],
                   c["longest_run_laps"]] for c in wk.compound_summary(all_runs)],
        ))

    if sprint is not None and len(sprint.results):
        tables.append(DataTable(
            key="sprint", section="weekend", title="Sprint result",
            columns=["Pos", "Driver", "Team", "Grid", "Status"],
            rows=[[r["pos"], r["driver"], team_code(r["team"]), r["grid"], r["status"]]
                  for r in wk.classification(sprint.results)],
        ))

    if race is not None and race_weather:
        w = wk.weather_summary(race.weather_data)
        if w:
            weather_rows.append(["Race (forecast stand-in)", w["air_c"], w["track_c"], w["humidity_pct"],
                                 w["wind_ms"], w["rain_share"]])
    if weather_rows:
        tables.append(DataTable(
            key="weather", section="weekend", title="Weather",
            columns=["Session", "Air (C)", "Track (C)", "Humidity (%)", "Wind (m/s)", "Share of samples with rain"],
            rows=weather_rows,
        ))

    if penalties or deletions:
        lines = penalties[-25:]
        if deletions:
            per_driver = {car_numbers.get(car, f"#{car}"): n for car, n in deletions.items()}
            lines.append("Track-limit lap deletions this weekend: "
                         + ", ".join(f"{d} x{n}" for d, n in sorted(per_driver.items(), key=lambda kv: -kv[1])))
        tables.append(DataTable(
            key="race_control", section="weekend", title="Race control: penalties & investigations",
            columns=["Message"], rows=[[m] for m in lines],
        ))

    # ---- season -----------------------------------------------------------
    say("Loading championship standings")
    tables += _season_tables(fastf1, year, round_number)

    # ---- history at this circuit -------------------------------------------
    tables += _history_tables(fastf1, key, year, history_years, say)

    weather_text = None
    if race is not None and race_weather:
        w = wk.weather_summary(race.weather_data)
        if w:
            weather_text = (f"Race day: air {w['air_c']}C, track {w['track_c']}C, "
                            f"{'rain at times' if (w['rain_share'] or 0) > 0 else 'dry'} "
                            "(observed conditions, used as the forecast)")
    if race is None:
        notes.append("The race has not been run yet: the grid is the qualifying order (penalties may be missing).")

    return RaceContext(
        year=year,
        round=round_number,
        event_name=str(event["EventName"]),
        weekend_format=str(event.get("EventFormat", "conventional")),
        circuit=circuit,
        drivers=list(drivers.values()),
        weather=weather_text,
        extra_notes=notes,
        tables=tables,
        data_sources=["FastF1 live timing", "Ergast (via FastF1)", "circuit reference table"],
        actual_result=actual,
    )


def _season_tables(fastf1: Any, year: int, round_number: int) -> list[DataTable]:
    if round_number <= 1:
        return []
    tables: list[DataTable] = []
    try:
        from fastf1.ergast import Ergast

        ergast = Ergast()
        ds = ergast.get_driver_standings(season=year, round=round_number - 1).content[0]
        tables.append(DataTable(
            key="driver_standings", section="season", title=f"Drivers' championship after round {round_number - 1}",
            columns=["Pos", "Driver", "Team", "Points", "Wins"],
            rows=[[int(r["position"]), r.get("driverCode"), team_code(_first(r.get("constructorNames"))),
                   float(r["points"]), int(r["wins"])] for _, r in ds.iterrows()],
        ))
        cs = ergast.get_constructor_standings(season=year, round=round_number - 1).content[0]
        tables.append(DataTable(
            key="constructor_standings", section="season", title="Constructors' championship",
            columns=["Pos", "Team", "Points", "Wins"],
            rows=[[int(r["position"]), team_code(r.get("constructorName")), float(r["points"]), int(r["wins"])]
                  for _, r in cs.iterrows()],
        ))
        recent = list(range(max(1, round_number - 3), round_number))
        finishes: dict[str, dict[int, str]] = {}
        for rnd in recent:
            res = ergast.get_race_results(season=year, round=rnd).content[0]
            for _, r in res.iterrows():
                status = str(r.get("status", ""))
                pos = str(int(r["position"])) if status.startswith(("Finished", "+")) or "Lap" in status else "DNF"
                finishes.setdefault(r.get("driverCode"), {})[rnd] = pos
        tables.append(DataTable(
            key="recent_form", section="season", title="Recent race finishes",
            columns=["Driver", *[f"R{r}" for r in recent]],
            rows=[[d, *[f.get(r, "-") for r in recent]] for d, f in sorted(finishes.items())],
        ))
    except Exception as exc:  # noqa: BLE001 - Ergast mirror down or season not covered
        logger.info("season tables unavailable: %s", exc)
    return tables


def _history_tables(fastf1: Any, key: str, year: int, years: int, say: Progress) -> list[DataTable]:
    summaries: list[dict[str, Any]] = []
    for past in range(year - 1, year - 1 - years, -1):
        try:
            schedule = fastf1.get_event_schedule(past, include_testing=False)
            match = [row for _, row in schedule.iterrows() if circuit_key_for_location(str(row["Location"])) == key]
            if not match:
                continue
            say(f"Loading {past} race at this circuit")
            race = _load(fastf1.get_event(past, int(match[0]["RoundNumber"])), "Race", laps=True)
            if race is None or race.laps is None or race.laps.empty:
                continue
            summaries.append(wk.race_history(past, race.laps, race.results))
        except Exception as exc:  # noqa: BLE001
            logger.info("history %s unavailable: %s", past, exc)
    if not summaries:
        return []
    tables = [DataTable(
        key="history_summary", section="history", title="Previous races at this circuit",
        columns=["Year", "Winner (grid)", "Classified", "DNFs", "Stops (count: drivers)", "Safety cars (laps)",
                 "VSCs (laps)", "Red flags", "Measured pit loss (s)"],
        rows=[[
            h["year"], f"{h['winner']} (P{h['winner_grid']})", h["classified"], ", ".join(h["dnfs"]) or "-",
            ", ".join(f"{k}: {v}" for k, v in h["stops_distribution"].items()),
            _periods(h["safety_cars"]), _periods(h["vscs"]), _periods(h["red_flags"]), h["measured_pit_loss_s"] or "-",
        ] for h in summaries],
    )]
    for h in summaries:
        tables.append(DataTable(
            key=f"history_{h['year']}", section="history", title=f"{h['year']} top 10 and strategies",
            columns=["Pos", "Driver", "Team", "Grid", "Tyres", "Pit laps"],
            rows=[[r["pos"], r["driver"], team_code(r["team"]), r["grid"], r["strategy"],
                   ", ".join(map(str, r["pit_laps"] or [])) or "-"] for r in h["top10"]],
            note="Lap-1 moves: " + ", ".join(f"{m['driver']} {m['gained']:+d}" for m in h["biggest_lap1_moves"])
            if h["biggest_lap1_moves"] else None,
        ))
    return tables


def _longest_per_compound(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in runs:
        k = (r["driver"], r["compound"])
        if k not in best or (r["laps"], -r["median_s"]) > (best[k]["laps"], -best[k]["median_s"]):
            best[k] = r
    return sorted(best.values(), key=lambda r: (r["compound"] or "", r["median_s"]))


def _periods(periods: list) -> str:
    return ", ".join(f"L{a}" if a == b else f"L{a}-{b}" for a, b in periods) or "-"


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return value


