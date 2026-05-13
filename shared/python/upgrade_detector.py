"""Statistical upgrade detection — Welch's t-test per dimension.

After every race we have a new fingerprint per team. We split the series into
two windows around race N: the 4 races BEFORE and the 3 races AFTER (including
N itself). If Welch's t-test produces ``p < 0.1`` on any dimension AND the
direction of change is favourable, we flag an upgrade event.

Welch's t-test (rather than Student's) because the two windows can have very
different variance after a real upgrade — assuming equal variance would mask
genuine shifts.
"""
from __future__ import annotations

import math
from typing import Any

from scipy import stats

from circuit_profiler import FINGERPRINT_DIMENSIONS

UPGRADE_PVAL_THRESHOLD = 0.10
MIN_PRE_SAMPLES = 3
MIN_POST_SAMPLES = 3
MIN_ABS_DELTA = 1.5  # filter out noise — require a meaningful absolute shift


def detect_upgrade_event(
    team_code: str,
    race_number: int,
    fingerprint_series: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Compare pre- and post-race fingerprint windows around ``race_number``.

    ``fingerprint_series`` is a list of dicts ordered chronologically:

        [{"race_round": 5, "dimensions": {...}}, ...]

    Returns ``None`` if no statistically significant shift is detected.
    """
    pre = [
        f["dimensions"]
        for f in fingerprint_series
        if f.get("race_round", 0) < race_number
    ][-6:]
    post = [
        f["dimensions"]
        for f in fingerprint_series
        if f.get("race_round", 0) >= race_number
    ][:6]

    if len(pre) < MIN_PRE_SAMPLES or len(post) < MIN_POST_SAMPLES:
        return None

    affected: list[str] = []
    deltas: dict[str, float] = {}
    p_values: dict[str, float] = {}

    for dim in FINGERPRINT_DIMENSIONS:
        pre_vals = [float(f.get(dim, 50)) for f in pre]
        post_vals = [float(f.get(dim, 50)) for f in post]
        if not pre_vals or not post_vals:
            continue

        delta = sum(post_vals) / len(post_vals) - sum(pre_vals) / len(pre_vals)
        if abs(delta) < MIN_ABS_DELTA:
            continue

        try:
            t_result = stats.ttest_ind(post_vals, pre_vals, equal_var=False)
            p = float(t_result.pvalue)
        except Exception:
            continue
        if math.isnan(p):
            continue
        p_values[dim] = round(p, 4)
        deltas[dim] = round(delta, 2)
        if p < UPGRADE_PVAL_THRESHOLD and delta > 0:
            affected.append(dim)

    if not affected:
        return None

    confidence = 1.0 - min(p_values[d] for d in affected)
    return {
        "team": team_code,
        "detected_at_race": race_number,
        "affected_dimensions": affected,
        "delta": {dim: deltas[dim] for dim in affected},
        "p_values": {dim: p_values[dim] for dim in affected},
        "confidence": round(confidence, 3),
        "notes": _notes_for_upgrade(affected, deltas),
    }


def _notes_for_upgrade(affected: list[str], deltas: dict[str, float]) -> str:
    """Heuristic explanation — translates the affected dimensions into a
    plausible upgrade description.
    """
    sets = {
        ("high_speed_cornering", "qualifying_pace"): "Likely floor or front-wing aero revision.",
        ("low_speed_cornering", "tyre_management"): "Mechanical / suspension upgrade — improved mechanical grip.",
        ("straight_line_speed",): "Power unit mode or low-drag rear wing.",
        ("tyre_strategy_execution",): "Operational improvement (pit crew or strategy software).",
        ("race_pace_conversion",): "Race-trim setup direction change — better balance under load.",
    }
    affected_tuple = tuple(sorted(affected))
    for signature, note in sets.items():
        if all(s in affected_tuple for s in signature):
            return note
    direction = ", ".join(f"{d} {deltas[d]:+.1f}" for d in affected)
    return f"Multiple dimensions shifted: {direction}"


def project_upgrade_impact(
    upgrade_event: dict[str, Any],
    upcoming_circuit_profile: dict[str, Any],
) -> dict[str, Any]:
    """Translate per-dimension upgrade deltas into a circuit-weighted lap-time
    benefit estimate. Heuristic — 1 fingerprint point ≈ 0.01 s at full circuit
    weight (calibrated against 2023 in-season examples).
    """
    POINT_TO_SECONDS = 0.01
    breakdown: dict[str, float] = {}
    for dim, delta in (upgrade_event.get("delta") or {}).items():
        weight = float(upcoming_circuit_profile.get(dim, 0.5))
        breakdown[dim] = round(delta * weight * POINT_TO_SECONDS, 3)
    projected_lap_delta = -round(sum(breakdown.values()), 3)  # negative = faster
    return {
        "per_dimension_seconds": breakdown,
        "projected_lap_delta": projected_lap_delta,
        "net_upgrade_benefit": (
            "Significant" if projected_lap_delta <= -0.05
            else "Moderate" if projected_lap_delta <= -0.02
            else "Low" if projected_lap_delta <= 0
            else "Negligible"
        ),
    }
