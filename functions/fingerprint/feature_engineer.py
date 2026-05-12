"""Compute the 8-dimension team performance fingerprint from race history.

Every dimension is normalised to a 0–100 percentile rank against the field
over a rolling window of recent races, then exponentially weighted so the most
recent race contributes ~2× the weight of a race eight rounds ago.

The inputs come straight from DynamoDB (lap records, results, pit stops). We
keep everything pure-function so the same code can be reused by the trainer
when building historical training rows (no data-leakage; only races BEFORE
the target race are passed in).
"""
from __future__ import annotations

import math
import statistics
from typing import Any

from circuit_profiler import FINGERPRINT_DIMENSIONS

DEFAULT_WINDOW = 8
DECAY_HALF_LIFE = 8.0  # races


def _exponential_weights(n: int, half_life: float = DECAY_HALF_LIFE) -> list[float]:
    """Return ``n`` weights where the most recent (last) has weight 1.0 and a
    race ``half_life`` events earlier has weight 0.5. Normalised to sum to 1.
    """
    raw = [math.pow(0.5, (n - 1 - i) / half_life) for i in range(n)]
    total = sum(raw)
    return [w / total for w in raw]


def _percentile_rank(value: float, distribution: list[float], lower_is_better: bool = False) -> float:
    """Where in ``distribution`` does ``value`` sit, as a 0–100 percentile?"""
    if not distribution:
        return 50.0
    sorted_dist = sorted(distribution)
    below = sum(1 for v in sorted_dist if v < value)
    pct = (below / len(sorted_dist)) * 100
    return round(100 - pct if lower_is_better else pct, 2)


def compute_team_fingerprint(
    team_code: str,
    race_history: list[dict[str, Any]],
    field_history: list[dict[str, Any]] | None = None,
    window: int = DEFAULT_WINDOW,
) -> dict[str, float]:
    """Build the 8-dim fingerprint for one team from the last ``window`` races.

    Each entry in ``race_history`` is a dict with per-race aggregate features:

        {
            "race_round": int,
            "year": int,
            "best_speed_st": float | None,        # max speed trap reading (km/h)
            "high_speed_sector_gap": float | None, # seconds vs fastest car in high-speed sectors
            "low_speed_sector_gap": float | None,
            "tyre_deg_rate": float | None,        # sec/lap loss per stint
            "qualifying_gap_to_pole": float | None, # seconds
            "race_finish_delta_from_grid": int | None,  # +N positions gained from grid
            "pit_consistency": float | None,      # stddev of pit stop times
            "wet_race": bool,
            "wet_finishing_rank": int | None,     # 1=best in wet sample
            "field_size": int,                    # how many entrants in the race
        }

    ``field_history`` is the same data for every other team — used to compute
    percentile ranks. When omitted, the function falls back to assuming a
    field-average around the 50th percentile.
    """
    if not race_history:
        return {dim: 50.0 for dim in FINGERPRINT_DIMENSIONS}

    recent = race_history[-window:]
    weights = _exponential_weights(len(recent))

    def weighted_mean(values: list[float | None]) -> float | None:
        pairs = [(v, w) for v, w in zip(values, weights) if v is not None]
        if not pairs:
            return None
        total_w = sum(w for _, w in pairs)
        return sum(v * w for v, w in pairs) / total_w

    field = field_history or []

    fingerprint: dict[str, float] = {}

    # 1. Straight-line speed — percentile rank of max speed trap (higher is better)
    own_speed = weighted_mean([r.get("best_speed_st") for r in recent])
    field_speeds = [r.get("best_speed_st") for r in field if r.get("best_speed_st") is not None]
    fingerprint["straight_line_speed"] = (
        _percentile_rank(own_speed, field_speeds) if own_speed is not None else 50.0
    )

    # 2. High-speed cornering — sector gap to fastest (lower gap is better)
    own_hs_gap = weighted_mean([r.get("high_speed_sector_gap") for r in recent])
    field_hs_gaps = [r.get("high_speed_sector_gap") for r in field if r.get("high_speed_sector_gap") is not None]
    fingerprint["high_speed_cornering"] = (
        _percentile_rank(own_hs_gap, field_hs_gaps, lower_is_better=True) if own_hs_gap is not None else 50.0
    )

    # 3. Low-speed cornering — same shape as high-speed
    own_ls_gap = weighted_mean([r.get("low_speed_sector_gap") for r in recent])
    field_ls_gaps = [r.get("low_speed_sector_gap") for r in field if r.get("low_speed_sector_gap") is not None]
    fingerprint["low_speed_cornering"] = (
        _percentile_rank(own_ls_gap, field_ls_gaps, lower_is_better=True) if own_ls_gap is not None else 50.0
    )

    # 4. Tyre management — degradation rate (lower is better)
    own_deg = weighted_mean([r.get("tyre_deg_rate") for r in recent])
    field_degs = [r.get("tyre_deg_rate") for r in field if r.get("tyre_deg_rate") is not None]
    fingerprint["tyre_management"] = (
        _percentile_rank(own_deg, field_degs, lower_is_better=True) if own_deg is not None else 50.0
    )

    # 5. Qualifying pace — gap to pole (lower is better)
    own_quali = weighted_mean([r.get("qualifying_gap_to_pole") for r in recent])
    field_qualis = [r.get("qualifying_gap_to_pole") for r in field if r.get("qualifying_gap_to_pole") is not None]
    fingerprint["qualifying_pace"] = (
        _percentile_rank(own_quali, field_qualis, lower_is_better=True) if own_quali is not None else 50.0
    )

    # 6. Race pace conversion — positions gained from grid (higher is better)
    own_conv = weighted_mean([
        float(r["race_finish_delta_from_grid"])
        for r in recent if r.get("race_finish_delta_from_grid") is not None
    ])
    field_convs = [r["race_finish_delta_from_grid"] for r in field if r.get("race_finish_delta_from_grid") is not None]
    fingerprint["race_pace_conversion"] = (
        _percentile_rank(own_conv, field_convs) if own_conv is not None else 50.0
    )

    # 7. Tyre strategy execution — pit consistency (lower stddev is better)
    own_pit = weighted_mean([r.get("pit_consistency") for r in recent])
    field_pits = [r.get("pit_consistency") for r in field if r.get("pit_consistency") is not None]
    fingerprint["tyre_strategy_execution"] = (
        _percentile_rank(own_pit, field_pits, lower_is_better=True) if own_pit is not None else 50.0
    )

    # 8. Wet weather — finishing rank in the wet (lower rank is better)
    wets = [r for r in recent if r.get("wet_race")]
    if wets:
        own_wet = statistics.mean([float(r["wet_finishing_rank"]) for r in wets if r.get("wet_finishing_rank")])
        field_wet = [r.get("wet_finishing_rank") for r in field if r.get("wet_race") and r.get("wet_finishing_rank")]
        fingerprint["wet_weather_performance"] = (
            _percentile_rank(own_wet, field_wet, lower_is_better=True) if field_wet else 50.0
        )
    else:
        fingerprint["wet_weather_performance"] = 50.0

    # Clamp results into [0, 100] and round for stability.
    return {dim: round(max(0.0, min(100.0, score)), 1) for dim, score in fingerprint.items()}


def compute_fingerprint_delta(
    fingerprint_before: dict[str, float],
    fingerprint_after: dict[str, float],
) -> dict[str, float]:
    """Per-dimension delta. Positive = improvement."""
    return {
        dim: round(float(fingerprint_after.get(dim, 50)) - float(fingerprint_before.get(dim, 50)), 2)
        for dim in FINGERPRINT_DIMENSIONS
    }
