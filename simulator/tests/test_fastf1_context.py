"""Full-weekend FastF1 context, exercised against the fake fastf1 module."""
from __future__ import annotations

import pytest

from simulator import fastf1_source, weekend
from simulator.tests import fake_fastf1


@pytest.fixture
def ctx(monkeypatch):
    import fastf1.ergast

    monkeypatch.setattr(fastf1_source, "_fastf1", lambda: fake_fastf1.make_module())
    monkeypatch.setattr(fastf1.ergast, "Ergast", fake_fastf1.FakeErgast)
    stages = []
    context = fastf1_source.from_fastf1(2024, 5, progress=stages.append)
    context._stages = stages  # type: ignore[attr-defined]
    return context


def test_context_has_every_section(ctx):
    keys = {t.key for t in ctx.tables}
    assert {"qualifying", "session_pace", "long_runs", "compounds", "weather", "race_control",
            "driver_standings", "constructor_standings", "recent_form", "history_summary"} <= keys
    assert {"history_2023", "history_2022", "history_2021"} <= keys
    assert any("Practice 2" in s for s in ctx._stages)


def test_grid_penalties_and_pit_lane_start(ctx):
    drivers = {d.code: d for d in ctx.drivers}
    assert drivers["VER"].grid == 1
    assert drivers["HAM"].grid is None and "pit lane" in drivers["HAM"].notes
    assert drivers["NOR"].quali_gap_s == pytest.approx(0.10, abs=1e-6)
    assert drivers["VER"].long_run_pace_s is not None


def test_actual_result_kept_out_of_prompt(ctx):
    assert ctx.actual_result and ctx.actual_result[0] == "VER"
    prompt = ctx.to_prompt()
    assert "## This weekend" in prompt and "## History at this circuit" in prompt
    assert "Engine" not in prompt  # the race's DNF status must not leak


def test_history_reads_safety_car_and_pit_loss(ctx):
    summary = next(t for t in ctx.tables if t.key == "history_summary")
    row = dict(zip(summary.columns, summary.rows[0]))
    assert row["Safety cars (laps)"] == "L20-22"
    assert float(row["Measured pit loss (s)"]) == pytest.approx(22.0, abs=1.5)  # +11s in-lap, +11s out-lap
    assert "RUS" in row["DNFs"]


def test_track_limits_mapped_to_driver(ctx):
    rc = next(t for t in ctx.tables if t.key == "race_control")
    flat = " ".join(r[0] for r in rc.rows)
    assert "GRID PENALTY" in flat
    assert "LEC x" in flat


def test_context_round_trips_through_cache(ctx, tmp_path):
    from simulator.store import ContextCache

    cache = ContextCache(tmp_path)
    cache.put(ctx, "fastf1")
    loaded = cache.get(2024, 5, "fastf1")
    assert loaded.actual_result == ctx.actual_result
    assert loaded.to_prompt() == ctx.to_prompt()
    assert cache.cached_rounds(2024) == {5: ["fastf1"]}


def test_long_run_degradation_is_fuel_corrected():
    laps = fake_fastf1._laps(20, race=False, seed=1, pit_lap=None)
    runs = weekend.long_runs(laps)
    ver = next(r for r in runs if r["driver"] == "VER")
    # synthetic tyre deg is 0.08 s/lap, fuel effect -0.05 s/lap
    assert ver["deg_s_per_lap"] == pytest.approx(0.08 + weekend.FUEL_EFFECT_S_PER_LAP - 0.05, abs=0.03)
