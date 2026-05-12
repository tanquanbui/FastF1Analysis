"""Training feature definitions — single source of truth for what goes into
the model. Reused by both the trainer (when assembling rows from DynamoDB) and
the predictor (when constructing inference inputs at race time).
"""
from __future__ import annotations

from typing import Any

# Order matters — the SageMaker XGBoost container expects CSV where the first
# column is the label and the remaining columns are features in fixed order.
TRAINING_FEATURES = [
    # Team fingerprint at time of race
    "team_straight_line_speed",
    "team_high_speed_cornering",
    "team_low_speed_cornering",
    "team_tyre_management",
    "team_qualifying_pace",
    "team_race_pace_conversion",
    "team_tyre_strategy_execution",
    "team_wet_weather_performance",
    # Circuit compatibility
    "track_compatibility_score",
    # Circuit profile (what the track rewards)
    "circuit_straight_speed_weight",
    "circuit_high_speed_weight",
    "circuit_low_speed_weight",
    "circuit_tyre_mgmt_weight",
    # Recent form (last 3 races)
    "avg_finishing_position_l3",
    "avg_qualifying_position_l3",
    "dnf_rate_l10",
    # Championship context
    "championship_position",
    "points_gap_to_leader",
    "races_remaining",
    "must_win_pressure",
    # Upgrade recency
    "races_since_last_upgrade",
    "upgrade_dimension_delta_max",
    # Session-specific (available Thursday before race)
    "practice_pace_rank",
    "qualifying_position",
    # Weather
    "rain_probability",
    "expected_temperature",
]

TARGET_COLUMN = "finishing_position_bracket"

# Multi-class buckets: P1, P2-3, P4-5, P6-10, P11+
POSITION_BUCKETS = {
    0: "P1",
    1: "P2-3",
    2: "P4-5",
    3: "P6-10",
    4: "P11+",
}


def position_to_bucket(position: int | None) -> int:
    """Map a finishing position to the categorical class index."""
    if position is None or position <= 0:
        return 4
    if position == 1:
        return 0
    if position <= 3:
        return 1
    if position <= 5:
        return 2
    if position <= 10:
        return 3
    return 4


def build_feature_row(
    *,
    team_fingerprint: dict[str, float],
    circuit_profile: dict[str, float],
    track_compatibility: float,
    recent_form: dict[str, float],
    championship_ctx: dict[str, Any],
    upgrade_ctx: dict[str, float],
    session_ctx: dict[str, float],
    weather_ctx: dict[str, float],
) -> dict[str, float]:
    """Assemble a feature row in canonical order. Returns dict so callers
    can validate the keys against ``TRAINING_FEATURES`` before encoding to CSV.
    """
    row: dict[str, float] = {}
    for dim_key, fp_key in [
        ("team_straight_line_speed", "straight_line_speed"),
        ("team_high_speed_cornering", "high_speed_cornering"),
        ("team_low_speed_cornering", "low_speed_cornering"),
        ("team_tyre_management", "tyre_management"),
        ("team_qualifying_pace", "qualifying_pace"),
        ("team_race_pace_conversion", "race_pace_conversion"),
        ("team_tyre_strategy_execution", "tyre_strategy_execution"),
        ("team_wet_weather_performance", "wet_weather_performance"),
    ]:
        row[dim_key] = float(team_fingerprint.get(fp_key, 50))

    row["track_compatibility_score"] = float(track_compatibility)
    row["circuit_straight_speed_weight"] = float(circuit_profile.get("straight_line_speed", 0.5))
    row["circuit_high_speed_weight"] = float(circuit_profile.get("high_speed_cornering", 0.5))
    row["circuit_low_speed_weight"] = float(circuit_profile.get("low_speed_cornering", 0.5))
    row["circuit_tyre_mgmt_weight"] = float(circuit_profile.get("tyre_management", 0.5))

    row["avg_finishing_position_l3"] = float(recent_form.get("avg_finishing_position_l3", 10))
    row["avg_qualifying_position_l3"] = float(recent_form.get("avg_qualifying_position_l3", 10))
    row["dnf_rate_l10"] = float(recent_form.get("dnf_rate_l10", 0.1))

    row["championship_position"] = float(championship_ctx.get("position", 10))
    row["points_gap_to_leader"] = float(championship_ctx.get("points_gap_to_leader", 0))
    row["races_remaining"] = float(championship_ctx.get("races_remaining", 0))
    row["must_win_pressure"] = float(championship_ctx.get("must_win_pressure", 0))

    row["races_since_last_upgrade"] = float(upgrade_ctx.get("races_since_last_upgrade", 99))
    row["upgrade_dimension_delta_max"] = float(upgrade_ctx.get("upgrade_dimension_delta_max", 0))

    row["practice_pace_rank"] = float(session_ctx.get("practice_pace_rank", 10))
    row["qualifying_position"] = float(session_ctx.get("qualifying_position", 10))

    row["rain_probability"] = float(weather_ctx.get("rain_probability", 0))
    row["expected_temperature"] = float(weather_ctx.get("expected_temperature", 25))

    return row


def row_to_csv(row: dict[str, float], label: int | None = None) -> str:
    """Format a feature row for the SageMaker XGBoost CSV protocol.

    XGBoost container expects ``label,feature_0,feature_1,...`` — label first,
    no header.
    """
    values = [str(row[name]) for name in TRAINING_FEATURES]
    if label is not None:
        return ",".join([str(label), *values])
    return ",".join(values)
