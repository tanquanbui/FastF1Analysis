"""Driver-level prediction scoring.

The model combines six interpretable signals into a 0-100 score per driver.
Weights are hand-tuned (not trained) — see README for the full rationale.

   final =  0.30 × qualifying_score      ← strongest single predictor
          + 0.20 × historical_score      ← same circuit, past seasons
          + 0.20 × recent_form_score     ← last 5 races finishing positions
          + 0.10 × overtaking_score      ← grid → finish delta
          + 0.10 × reliability_score     ← 1 - DNF rate
          + 0.10 × track_fit_score       ← team fingerprint × circuit profile

When a signal has no data (early-season → no recent form, no quali yet, etc.)
its weight is redistributed across the remaining signals so the score stays
on a 0-100 scale.
"""
from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS = {
    "qualifying": 0.30,
    "historical": 0.20,
    "recent_form": 0.20,
    "overtaking": 0.10,
    "reliability": 0.10,
    "track_fit": 0.10,
}


def score_driver(
    qualifying_pos: int | None,
    historical_positions: list[int],
    recent_positions: list[int],
    grid_to_finish_history: list[int],
    dnf_rate: float | None,
    track_fit_score: float | None,
    wet_likely: bool = False,
    wet_history_positions: list[int] | None = None,
    field_size: int = 20,
) -> dict[str, Any]:
    """Return a per-driver score dict including breakdown for the UI.

    All position inputs are 1-based race positions; None means no data.
    """
    signals: dict[str, float | None] = {
        "qualifying": _pos_to_score(qualifying_pos, field_size) if qualifying_pos else None,
        "historical": _avg_pos_to_score(historical_positions, field_size),
        "recent_form": _avg_pos_to_score(recent_positions, field_size),
        "overtaking": _gain_to_score(grid_to_finish_history),
        "reliability": (1 - dnf_rate) * 100 if dnf_rate is not None else None,
        "track_fit": track_fit_score,
    }

    # Replace recent/historical with wet-only history if the race is wet.
    if wet_likely and wet_history_positions:
        signals["recent_form"] = _avg_pos_to_score(wet_history_positions, field_size)

    # Distribute weight only among present signals.
    weights = {k: w for k, w in DEFAULT_WEIGHTS.items() if signals.get(k) is not None}
    total_w = sum(weights.values()) or 1
    weights = {k: round(w / total_w, 3) for k, w in weights.items()}

    combined = sum(signals[k] * weights[k] for k in weights)
    return {
        "combined": round(combined, 1),
        "signals": {k: (round(v, 1) if v is not None else None) for k, v in signals.items()},
        "weights": weights,
    }


def _pos_to_score(position: int | None, field_size: int) -> float | None:
    """Map a 1-based position to a 0-100 score. P1 → 100, P_last → 0."""
    if not position or position < 1:
        return None
    return max(0.0, 100.0 * (field_size - position) / max(1, field_size - 1))


def _avg_pos_to_score(positions: list[int], field_size: int) -> float | None:
    valid = [p for p in (positions or []) if isinstance(p, (int, float)) and p > 0]
    if not valid:
        return None
    avg = sum(valid) / len(valid)
    return _pos_to_score(avg, field_size)


def _gain_to_score(grid_to_finish_history: list[int]) -> float | None:
    """Average positions gained from grid → finish. +5 = mid-pack overtaker,
    -3 = struggles. Map [-10, +10] → [0, 100]."""
    valid = [g for g in (grid_to_finish_history or []) if isinstance(g, (int, float))]
    if not valid:
        return None
    avg = sum(valid) / len(valid)
    # Anchor: +5 average gain → 75, +0 → 50, -5 → 25.
    return max(0.0, min(100.0, 50.0 + avg * 5.0))
