"""Tests for fingerprint computation."""
from __future__ import annotations

import math

import pytest

import feature_engineer


def _race(round_num, **overrides):
    base = {
        "race_round": round_num,
        "year": 2024,
        "best_speed_st": 330,
        "high_speed_sector_gap": 0.3,
        "low_speed_sector_gap": 0.4,
        "tyre_deg_rate": 0.05,
        "qualifying_gap_to_pole": 0.4,
        "race_finish_delta_from_grid": 1,
        "pit_consistency": 0.2,
        "wet_race": False,
        "wet_finishing_rank": None,
        "field_size": 20,
    }
    base.update(overrides)
    return base


class TestExponentialWeights:
    def test_recent_race_weighted_higher(self):
        weights = feature_engineer._exponential_weights(8, half_life=8)
        assert weights[-1] > weights[0]
        # With half_life=8 over 8 races the decay is over (n-1)/half_life = 7/8
        # half-lives — so newest carries ~2^(7/8) ≈ 1.83x the oldest.
        ratio = weights[-1] / weights[0]
        assert 1.7 < ratio < 2.0
        assert math.isclose(sum(weights), 1.0)

    def test_half_life_exact_double_when_n_matches(self):
        """Sanity check: when (n-1) == half_life the ratio is exactly 2."""
        weights = feature_engineer._exponential_weights(9, half_life=8)
        assert math.isclose(weights[-1] / weights[0], 2.0, rel_tol=1e-6)

    def test_normalised_to_sum_1(self):
        weights = feature_engineer._exponential_weights(5)
        assert math.isclose(sum(weights), 1.0)


class TestPercentileRank:
    def test_top_of_distribution_returns_100(self):
        assert feature_engineer._percentile_rank(100, [10, 20, 30, 40, 50]) == 100

    def test_bottom_of_distribution_returns_0(self):
        assert feature_engineer._percentile_rank(0, [10, 20, 30, 40, 50]) == 0

    def test_lower_is_better_inverts_score(self):
        rank = feature_engineer._percentile_rank(10, [10, 20, 30, 40, 50], lower_is_better=True)
        # 10 is the lowest — best when lower is better → 100
        assert rank > 80

    def test_empty_distribution_returns_50(self):
        assert feature_engineer._percentile_rank(42, []) == 50.0


class TestComputeTeamFingerprint:
    def test_returns_all_dimensions(self):
        history = [_race(i) for i in range(1, 5)]
        fp = feature_engineer.compute_team_fingerprint("RBR", history)
        for dim in feature_engineer.FINGERPRINT_DIMENSIONS:
            assert dim in fp
            assert 0 <= fp[dim] <= 100

    def test_empty_history_returns_neutral_50(self):
        fp = feature_engineer.compute_team_fingerprint("RBR", [])
        assert all(score == 50.0 for score in fp.values())

    def test_fast_car_against_slow_field_high_speed_rank(self):
        own_history = [_race(i, best_speed_st=340) for i in range(1, 5)]
        field = [_race(i, best_speed_st=320) for i in range(1, 5)] * 5
        fp = feature_engineer.compute_team_fingerprint("RBR", own_history, field)
        assert fp["straight_line_speed"] > 60

    def test_wet_weather_uses_only_wet_samples(self):
        history = [
            _race(1, wet_race=True, wet_finishing_rank=1),
            _race(2, wet_race=False),
            _race(3, wet_race=True, wet_finishing_rank=2),
        ]
        field = [
            _race(1, wet_race=True, wet_finishing_rank=10),
            _race(3, wet_race=True, wet_finishing_rank=8),
        ] * 5
        fp = feature_engineer.compute_team_fingerprint("RBR", history, field)
        assert fp["wet_weather_performance"] > 50


class TestComputeFingerprintDelta:
    def test_returns_per_dimension_delta(self):
        before = {dim: 50 for dim in feature_engineer.FINGERPRINT_DIMENSIONS}
        after = {dim: 60 for dim in feature_engineer.FINGERPRINT_DIMENSIONS}
        delta = feature_engineer.compute_fingerprint_delta(before, after)
        assert all(v == 10.0 for v in delta.values())

    def test_missing_dims_default_to_50(self):
        before = {"straight_line_speed": 50}
        after = {"straight_line_speed": 70}
        delta = feature_engineer.compute_fingerprint_delta(before, after)
        assert delta["straight_line_speed"] == 20.0
        # Other dims compared as 50 vs 50 = 0
        assert delta["tyre_management"] == 0
