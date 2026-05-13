"""Tests for circuit profile lookup + compatibility scoring."""
from __future__ import annotations

import pytest

import circuit_profiler


def test_known_circuit_returns_full_profile():
    profile = circuit_profiler.get_profile("monaco")
    assert profile is not None
    assert profile["low_speed_cornering"] == 0.95
    assert profile["straight_line_speed"] == 0.15


def test_unknown_circuit_returns_none():
    assert circuit_profiler.get_profile("middle-of-nowhere") is None


def test_compatibility_high_when_team_aligns_with_circuit():
    """A car that's all about low-speed grip should have Monaco-rewarded
    dimensions show up as strengths."""
    team = {
        "straight_line_speed": 20,
        "high_speed_cornering": 15,
        "low_speed_cornering": 95,
        "tyre_management": 90,
        "qualifying_pace": 95,
        "race_pace_conversion": 30,
        "tyre_strategy_execution": 80,
        "wet_weather_performance": 70,
    }
    monaco = circuit_profiler.get_profile("monaco")
    result = circuit_profiler.compute_track_compatibility(team, monaco)
    assert "low_speed_cornering" in result["strengths_exploited"]
    assert "qualifying_pace" in result["strengths_exploited"]
    assert result["overall_score"] > 35


def test_compatibility_low_for_mismatched_team():
    """Same low-speed specialist suffers at Monza."""
    team = {
        "straight_line_speed": 20,
        "high_speed_cornering": 15,
        "low_speed_cornering": 95,
        "tyre_management": 90,
        "qualifying_pace": 95,
        "race_pace_conversion": 30,
        "tyre_strategy_execution": 80,
        "wet_weather_performance": 70,
    }
    monza = circuit_profiler.get_profile("monza")
    result = circuit_profiler.compute_track_compatibility(team, monza)
    # straight_line_speed is weighted 0.95 here but team scores 20
    assert "straight_line_speed" in result["weaknesses_exposed"]


def test_missing_team_dimensions_treated_as_50():
    """Partial fingerprint shouldn't error — missing dims default to 50."""
    team = {"qualifying_pace": 80}
    monaco = circuit_profiler.get_profile("monaco")
    result = circuit_profiler.compute_track_compatibility(team, monaco)
    assert "overall_score" in result
    assert 0 <= result["overall_score"] <= 100


def test_verdict_text_scales_with_score():
    weak = circuit_profiler._verdict_for_score(20)
    strong = circuit_profiler._verdict_for_score(80)
    assert "Critical" in weak or "Weak" in weak
    assert "Strong" in strong or "Moderate" in strong
