"""Tests for the Monte Carlo championship simulator."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "functions" / "fingerprint"))

import championship_sim


def _standings():
    return {
        "drivers": [
            {"driver_code": "VER", "team_code": "RBR", "points": 250},
            {"driver_code": "NOR", "team_code": "MCL", "points": 220},
            {"driver_code": "LEC", "team_code": "FER", "points": 180},
        ],
        "constructors": [
            {"team_code": "RBR", "points": 450},
            {"team_code": "MCL", "points": 410},
            {"team_code": "FER", "points": 370},
        ],
    }


class TestSimulateChampionship:
    def test_returns_normalised_probabilities(self):
        result = championship_sim.simulate_championship(
            current_standings=_standings(),
            remaining_races=[{"name": f"r{i}"} for i in range(1, 4)],
            position_distributions={
                "VER": {1: 0.5, 2: 0.3, 3: 0.2},
                "NOR": {1: 0.3, 2: 0.4, 3: 0.3},
                "LEC": {1: 0.2, 2: 0.3, 3: 0.5},
            },
            n_simulations=500,
        )
        total = sum(result["title_probabilities"].values())
        assert total == pytest.approx(1.0, abs=0.05)
        assert "VER" in result["title_probabilities"]

    def test_leader_with_huge_gap_wins_most(self):
        standings = _standings()
        standings["drivers"][0]["points"] = 1000
        result = championship_sim.simulate_championship(
            current_standings=standings,
            remaining_races=[{"name": "finale"}],
            position_distributions={
                "VER": {1: 0.5, 2: 0.3, 3: 0.2},
                "NOR": {1: 0.3, 2: 0.4, 3: 0.3},
                "LEC": {1: 0.2, 2: 0.3, 3: 0.5},
            },
            n_simulations=500,
        )
        assert result["title_probabilities"]["VER"] > 0.95

    def test_empty_remaining_races_returns_empty(self):
        result = championship_sim.simulate_championship(
            current_standings=_standings(),
            remaining_races=[],
            position_distributions={},
            n_simulations=10,
        )
        assert result["title_probabilities"] == {}

    def test_expected_points_increase_with_more_races(self):
        result = championship_sim.simulate_championship(
            current_standings=_standings(),
            remaining_races=[{"name": f"r{i}"} for i in range(1, 11)],
            position_distributions={"VER": {1: 1.0}},  # always wins
            n_simulations=200,
        )
        # VER scoring full 25/race over 10 races starting at 250 → 500
        assert result["expected_points"]["VER"] >= 480
