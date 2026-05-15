"""Tests for the structured pre-race report builder."""
from __future__ import annotations

import pytest

import report_builder


def _fingerprint(**overrides):
    base = {
        "straight_line_speed": 75,
        "high_speed_cornering": 80,
        "low_speed_cornering": 60,
        "tyre_management": 85,
        "qualifying_pace": 78,
        "race_pace_conversion": 72,
        "tyre_strategy_execution": 70,
        "wet_weather_performance": 65,
    }
    base.update(overrides)
    return base


def _compat(strengths=None, weaknesses=None, score=60.0):
    return {
        "overall_score": score,
        "verdict": "Moderate fit",
        "strengths_exploited": strengths or ["tyre_management"],
        "weaknesses_exposed": weaknesses or ["low_speed_cornering"],
        "dimension_scores": {dim: 60 for dim in [
            "straight_line_speed", "high_speed_cornering", "low_speed_cornering",
            "tyre_management", "qualifying_pace", "race_pace_conversion",
            "tyre_strategy_execution", "wet_weather_performance",
        ]},
    }


class TestBuildTeamRaceReport:
    def test_returns_full_schema(self):
        report = report_builder.build_team_race_report(
            team_code="RBR",
            team_name="Red Bull Racing",
            upcoming_race={"name": "Monaco Grand Prix", "round": 8, "year": 2024},
            current_fingerprint=_fingerprint(),
            compatibility=_compat(),
            last_upgrade=None,
            upgrade_impact=None,
            championship_position=1,
            championship_points_gap=0,
            races_remaining=15,
            model_prediction={"bracket": 1, "confidence": 0.7, "dnf_probability": 0.06},
        )
        assert report["team_code"] == "RBR"
        assert report["round"] == 8
        assert report["prediction"]["race"]["predicted_bracket"] == "P2-3"
        assert 1 <= report["prediction"]["race"]["position_range"][0] <= report["prediction"]["race"]["position_range"][1]
        assert report["championship_scenarios"]["current_position"] == 1
        assert isinstance(report["strengths"], list)
        assert isinstance(report["weaknesses"], list)

    def test_must_win_flag_triggers_when_close_to_end_of_season(self):
        report = report_builder.build_team_race_report(
            team_code="MCL",
            team_name="McLaren",
            upcoming_race={"name": "Las Vegas", "round": 22, "year": 2024},
            current_fingerprint=_fingerprint(),
            compatibility=_compat(),
            last_upgrade=None,
            upgrade_impact=None,
            championship_position=2,
            championship_points_gap=35,
            races_remaining=2,
            model_prediction={"bracket": 0, "confidence": 0.6, "dnf_probability": 0.05},
        )
        assert report["championship_scenarios"]["must_win_race"] is True
        assert report["championship_scenarios"]["pressure_level"] == "Critical"

    def test_upgrade_section_included_when_present(self):
        report = report_builder.build_team_race_report(
            team_code="FER",
            team_name="Ferrari",
            upcoming_race={"name": "Monza", "round": 16, "year": 2024},
            current_fingerprint=_fingerprint(),
            compatibility=_compat(),
            last_upgrade={
                "detected_at_race": 12,
                "affected_dimensions": ["straight_line_speed"],
                "confidence": 0.85,
                "delta": {"straight_line_speed": 6.0},
                "notes": "Low-drag rear wing.",
            },
            upgrade_impact={"projected_lap_delta": -0.05, "net_upgrade_benefit": "Moderate"},
            championship_position=3,
            championship_points_gap=80,
            races_remaining=8,
            model_prediction={"bracket": 1, "confidence": 0.65, "dnf_probability": 0.07},
        )
        assert report["upgrade_analysis"] is not None
        assert report["upgrade_analysis"]["last_upgrade_detected"]["race"] == 12
        assert report["upgrade_analysis"]["upgrade_impact_at_this_circuit"]["projected_lap_delta"] == -0.05

    def test_p1_bracket_returns_position_1(self):
        report = report_builder.build_team_race_report(
            team_code="RBR",
            team_name="Red Bull",
            upcoming_race={"name": "Test", "round": 1, "year": 2024},
            current_fingerprint=_fingerprint(),
            compatibility=_compat(score=85),
            last_upgrade=None,
            upgrade_impact=None,
            championship_position=1,
            championship_points_gap=0,
            races_remaining=22,
            model_prediction={"bracket": 0, "confidence": 0.9, "dnf_probability": 0.04},
        )
        assert report["prediction"]["race"]["position_range"] == [1, 1]
        assert report["prediction"]["race"]["predicted_bracket"] == "P1"
