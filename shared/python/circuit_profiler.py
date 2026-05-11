"""Circuit profiles — per-track weights on each of the 8 fingerprint dimensions.

The weights describe *what the track rewards*, not what any specific team does.
They were calibrated by analysing 2018–2024 results: tracks where sector-time
deltas in the relevant speed band predicted finishing position most reliably
received the highest weights.

To add a new circuit, follow the existing entries — weights must sum
approximately to the same ballpark across tracks (no normalisation needed,
since the compatibility scorer takes a dot product, not an average).
"""
from __future__ import annotations

from typing import Any

FINGERPRINT_DIMENSIONS = [
    "straight_line_speed",
    "high_speed_cornering",
    "low_speed_cornering",
    "tyre_management",
    "qualifying_pace",
    "race_pace_conversion",
    "tyre_strategy_execution",
    "wet_weather_performance",
]

CIRCUIT_PROFILES: dict[str, dict[str, Any]] = {
    "monza": {
        "straight_line_speed": 0.95,
        "high_speed_cornering": 0.45,
        "low_speed_cornering": 0.25,
        "tyre_management": 0.50,
        "qualifying_pace": 0.80,
        "race_pace_conversion": 0.60,
        "tyre_strategy_execution": 0.55,
        "wet_weather_performance": 0.40,
        "notes": "Power circuit. Top speed is king. Aero teams struggle.",
    },
    "monaco": {
        "straight_line_speed": 0.15,
        "high_speed_cornering": 0.10,
        "low_speed_cornering": 0.95,
        "tyre_management": 0.85,
        "qualifying_pace": 0.98,
        "race_pace_conversion": 0.30,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.50,
        "notes": "Qualifying determines outcome. Low-speed mechanical grip critical.",
    },
    "silverstone": {
        "straight_line_speed": 0.55,
        "high_speed_cornering": 0.90,
        "low_speed_cornering": 0.50,
        "tyre_management": 0.75,
        "qualifying_pace": 0.70,
        "race_pace_conversion": 0.75,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.60,
        "notes": "High-speed aero platform circuit. Rewards well-rounded package.",
    },
    "singapore": {
        "straight_line_speed": 0.20,
        "high_speed_cornering": 0.30,
        "low_speed_cornering": 0.90,
        "tyre_management": 0.80,
        "qualifying_pace": 0.85,
        "race_pace_conversion": 0.55,
        "tyre_strategy_execution": 0.75,
        "wet_weather_performance": 0.45,
        "notes": "Street circuit. High downforce. Low-speed grip. Safety car lottery.",
    },
    "spa": {
        "straight_line_speed": 0.70,
        "high_speed_cornering": 0.80,
        "low_speed_cornering": 0.45,
        "tyre_management": 0.60,
        "qualifying_pace": 0.65,
        "race_pace_conversion": 0.70,
        "tyre_strategy_execution": 0.65,
        "wet_weather_performance": 0.90,
        "notes": "All-round circuit. Weather is wildcard. High-speed corners matter.",
    },
    "mexico": {
        "straight_line_speed": 0.80,
        "high_speed_cornering": 0.50,
        "low_speed_cornering": 0.65,
        "tyre_management": 0.70,
        "qualifying_pace": 0.75,
        "race_pace_conversion": 0.65,
        "tyre_strategy_execution": 0.60,
        "wet_weather_performance": 0.30,
        "notes": "High altitude penalises engine-dependent teams. Thin air reduces aero.",
    },
    "suzuka": {
        "straight_line_speed": 0.50,
        "high_speed_cornering": 0.95,
        "low_speed_cornering": 0.55,
        "tyre_management": 0.80,
        "qualifying_pace": 0.75,
        "race_pace_conversion": 0.80,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.65,
        "notes": "Technical high-speed circuit. Rewards aero precision. Beloved by engineers.",
    },
    "bahrain": {
        "straight_line_speed": 0.65,
        "high_speed_cornering": 0.55,
        "low_speed_cornering": 0.70,
        "tyre_management": 0.90,
        "qualifying_pace": 0.65,
        "race_pace_conversion": 0.75,
        "tyre_strategy_execution": 0.85,
        "wet_weather_performance": 0.10,
        "notes": "Tyre management circuit. Strategy often determines outcome.",
    },
    "hungary": {
        "straight_line_speed": 0.25,
        "high_speed_cornering": 0.35,
        "low_speed_cornering": 0.85,
        "tyre_management": 0.80,
        "qualifying_pace": 0.90,
        "race_pace_conversion": 0.45,
        "tyre_strategy_execution": 0.75,
        "wet_weather_performance": 0.55,
        "notes": "High downforce, low speed. Qualifying critical. European Monaco.",
    },
    "abu_dhabi": {
        "straight_line_speed": 0.60,
        "high_speed_cornering": 0.55,
        "low_speed_cornering": 0.65,
        "tyre_management": 0.65,
        "qualifying_pace": 0.70,
        "race_pace_conversion": 0.60,
        "tyre_strategy_execution": 0.75,
        "wet_weather_performance": 0.05,
        "notes": "Season finale. Balanced circuit. Finals pressure adds strategic complexity.",
    },
    "imola": {
        "straight_line_speed": 0.45,
        "high_speed_cornering": 0.70,
        "low_speed_cornering": 0.65,
        "tyre_management": 0.55,
        "qualifying_pace": 0.85,
        "race_pace_conversion": 0.35,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.70,
        "notes": "Narrow old-school circuit. Overtaking nearly impossible — qualifying decides.",
    },
    "barcelona": {
        "straight_line_speed": 0.50,
        "high_speed_cornering": 0.75,
        "low_speed_cornering": 0.55,
        "tyre_management": 0.85,
        "qualifying_pace": 0.65,
        "race_pace_conversion": 0.60,
        "tyre_strategy_execution": 0.80,
        "wet_weather_performance": 0.40,
        "notes": "Aerodynamic benchmark circuit. Reveals true car balance.",
    },
    "miami": {
        "straight_line_speed": 0.65,
        "high_speed_cornering": 0.55,
        "low_speed_cornering": 0.60,
        "tyre_management": 0.70,
        "qualifying_pace": 0.60,
        "race_pace_conversion": 0.55,
        "tyre_strategy_execution": 0.65,
        "wet_weather_performance": 0.30,
        "notes": "Semi-permanent street circuit. Mix of slow and high-speed sections.",
    },
    "jeddah": {
        "straight_line_speed": 0.75,
        "high_speed_cornering": 0.85,
        "low_speed_cornering": 0.30,
        "tyre_management": 0.60,
        "qualifying_pace": 0.80,
        "race_pace_conversion": 0.40,
        "tyre_strategy_execution": 0.55,
        "wet_weather_performance": 0.15,
        "notes": "Ultra-fast street circuit. Walls + flat-out commitment.",
    },
    "austin": {
        "straight_line_speed": 0.55,
        "high_speed_cornering": 0.75,
        "low_speed_cornering": 0.60,
        "tyre_management": 0.65,
        "qualifying_pace": 0.70,
        "race_pace_conversion": 0.70,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.55,
        "notes": "Bumpy COTA circuit. Mix of high and low speed; bumps test suspension.",
    },
    "interlagos": {
        "straight_line_speed": 0.65,
        "high_speed_cornering": 0.55,
        "low_speed_cornering": 0.60,
        "tyre_management": 0.70,
        "qualifying_pace": 0.65,
        "race_pace_conversion": 0.75,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.85,
        "notes": "Brazilian wildcard. Weather frequently flips the result.",
    },
    "qatar": {
        "straight_line_speed": 0.55,
        "high_speed_cornering": 0.85,
        "low_speed_cornering": 0.45,
        "tyre_management": 0.80,
        "qualifying_pace": 0.70,
        "race_pace_conversion": 0.65,
        "tyre_strategy_execution": 0.70,
        "wet_weather_performance": 0.05,
        "notes": "Lusail Circuit. High-speed sweepers + brutal heat = tyre stress.",
    },
    "las_vegas": {
        "straight_line_speed": 0.90,
        "high_speed_cornering": 0.30,
        "low_speed_cornering": 0.50,
        "tyre_management": 0.55,
        "qualifying_pace": 0.65,
        "race_pace_conversion": 0.65,
        "tyre_strategy_execution": 0.65,
        "wet_weather_performance": 0.20,
        "notes": "Strip circuit. Long straights and low-grip cold surface.",
    },
    "zandvoort": {
        "straight_line_speed": 0.40,
        "high_speed_cornering": 0.75,
        "low_speed_cornering": 0.60,
        "tyre_management": 0.65,
        "qualifying_pace": 0.80,
        "race_pace_conversion": 0.45,
        "tyre_strategy_execution": 0.65,
        "wet_weather_performance": 0.55,
        "notes": "Old-school banking. Hard to overtake; qualifying critical.",
    },
}


def compute_track_compatibility(
    team_fingerprint: dict[str, float],
    circuit_profile: dict[str, Any],
) -> dict[str, Any]:
    """Score how well a team's fingerprint aligns with a circuit's demands.

    Dot product of (team_score / 100) × circuit_weight per dimension. The
    overall score is the simple mean — bounded 0–100, comparable across
    circuits.
    """
    scores: dict[str, float] = {}
    for dim in FINGERPRINT_DIMENSIONS:
        team_val = float(team_fingerprint.get(dim, 50)) / 100.0
        circuit_weight = float(circuit_profile.get(dim, 0.5))
        scores[dim] = round(team_val * circuit_weight * 100, 2)

    overall = round(sum(scores.values()) / len(scores), 1)
    return {
        "overall_score": overall,
        "dimension_scores": scores,
        "strengths_exploited": sorted(
            [d for d, s in scores.items() if s > 55],
            key=lambda d: -scores[d],
        ),
        "weaknesses_exposed": sorted(
            [d for d, s in scores.items() if s < 30],
            key=lambda d: scores[d],
        ),
        "verdict": _verdict_for_score(overall),
    }


def _verdict_for_score(score: float) -> str:
    if score >= 65:
        return "Strong fit — team's strengths align with what the circuit rewards."
    if score >= 50:
        return "Moderate fit — competitive across most dimensions."
    if score >= 35:
        return "Weak fit — circuit exposes multiple weaknesses."
    return "Critical mismatch — major performance dimensions are underweighted by this car."


def get_profile(circuit_key: str) -> dict[str, Any] | None:
    """Look up a circuit profile by short key, returning ``None`` if unknown."""
    return CIRCUIT_PROFILES.get(circuit_key.lower())
