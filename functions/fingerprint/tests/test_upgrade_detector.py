"""Tests for the statistical upgrade detector."""
from __future__ import annotations

import pytest

import upgrade_detector


def _series(values_per_round):
    """Build a fingerprint_series from a dict {round: {dim: value, ...}}."""
    return [
        {"race_round": rnd, "dimensions": dims}
        for rnd, dims in sorted(values_per_round.items())
    ]


class TestDetectUpgradeEvent:
    def test_flags_significant_high_speed_improvement(self):
        series = _series({
            1: {"high_speed_cornering": 60, "qualifying_pace": 58, "tyre_management": 50, "low_speed_cornering": 55, "straight_line_speed": 50, "race_pace_conversion": 50, "tyre_strategy_execution": 50, "wet_weather_performance": 50},
            2: {"high_speed_cornering": 61, "qualifying_pace": 57, "tyre_management": 52, "low_speed_cornering": 54, "straight_line_speed": 51, "race_pace_conversion": 51, "tyre_strategy_execution": 50, "wet_weather_performance": 50},
            3: {"high_speed_cornering": 59, "qualifying_pace": 59, "tyre_management": 51, "low_speed_cornering": 56, "straight_line_speed": 49, "race_pace_conversion": 49, "tyre_strategy_execution": 51, "wet_weather_performance": 50},
            4: {"high_speed_cornering": 62, "qualifying_pace": 58, "tyre_management": 50, "low_speed_cornering": 55, "straight_line_speed": 50, "race_pace_conversion": 50, "tyre_strategy_execution": 50, "wet_weather_performance": 50},
            # ↓ upgrade at race 5 ↓
            5: {"high_speed_cornering": 72, "qualifying_pace": 68, "tyre_management": 51, "low_speed_cornering": 55, "straight_line_speed": 51, "race_pace_conversion": 51, "tyre_strategy_execution": 50, "wet_weather_performance": 50},
            6: {"high_speed_cornering": 75, "qualifying_pace": 70, "tyre_management": 50, "low_speed_cornering": 56, "straight_line_speed": 50, "race_pace_conversion": 50, "tyre_strategy_execution": 51, "wet_weather_performance": 50},
            7: {"high_speed_cornering": 74, "qualifying_pace": 69, "tyre_management": 52, "low_speed_cornering": 55, "straight_line_speed": 51, "race_pace_conversion": 49, "tyre_strategy_execution": 50, "wet_weather_performance": 50},
        })
        event = upgrade_detector.detect_upgrade_event("RBR", 5, series)
        assert event is not None
        assert "high_speed_cornering" in event["affected_dimensions"]
        assert event["delta"]["high_speed_cornering"] > 0
        assert event["confidence"] > 0.8

    def test_returns_none_when_stable(self):
        """Flat performance across the season — no upgrade detectable."""
        series = _series({
            i: {dim: 55 + (i % 3) for dim in upgrade_detector.FINGERPRINT_DIMENSIONS}
            for i in range(1, 9)
        })
        assert upgrade_detector.detect_upgrade_event("RBR", 5, series) is None

    def test_returns_none_when_too_few_samples(self):
        series = _series({
            1: {dim: 50 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            2: {dim: 70 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
        })
        assert upgrade_detector.detect_upgrade_event("RBR", 2, series) is None

    def test_returns_none_when_team_regresses(self):
        """A statistically significant DROP shouldn't be flagged as an upgrade."""
        series = _series({
            1: {dim: 75 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            2: {dim: 74 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            3: {dim: 76 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            4: {dim: 75 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            5: {dim: 55 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            6: {dim: 54 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
            7: {dim: 56 for dim in upgrade_detector.FINGERPRINT_DIMENSIONS},
        })
        assert upgrade_detector.detect_upgrade_event("RBR", 5, series) is None


class TestProjectUpgradeImpact:
    def test_high_relevance_circuit_yields_larger_benefit(self):
        upgrade = {"delta": {"straight_line_speed": 5.0}}
        monza_profile = {"straight_line_speed": 0.95}
        monaco_profile = {"straight_line_speed": 0.15}
        monza_impact = upgrade_detector.project_upgrade_impact(upgrade, monza_profile)
        monaco_impact = upgrade_detector.project_upgrade_impact(upgrade, monaco_profile)
        # Greater absolute lap delta at Monza than Monaco for the same upgrade.
        assert abs(monza_impact["projected_lap_delta"]) > abs(monaco_impact["projected_lap_delta"])

    def test_empty_delta_returns_zero_impact(self):
        impact = upgrade_detector.project_upgrade_impact({"delta": {}}, {"straight_line_speed": 0.5})
        assert impact["projected_lap_delta"] == 0
