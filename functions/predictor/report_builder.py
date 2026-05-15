"""Compose the per-team pre-race intelligence report.

Brings together:
  * the team's current fingerprint
  * the upcoming circuit's profile and compatibility score
  * the latest upgrade event for the team
  * the model's bucket prediction + qualifying-context
  * championship implications for the top contenders
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


POSITION_BUCKET_LABELS = ["P1", "P2-3", "P4-5", "P6-10", "P11+"]
BUCKET_RANGES = {0: (1, 1), 1: (2, 3), 2: (4, 5), 3: (6, 10), 4: (11, 20)}


def build_team_race_report(
    *,
    team_code: str,
    team_name: str,
    upcoming_race: dict[str, Any],
    current_fingerprint: dict[str, float],
    compatibility: dict[str, Any],
    last_upgrade: dict[str, Any] | None,
    upgrade_impact: dict[str, Any] | None,
    championship_position: int,
    championship_points_gap: int,
    races_remaining: int,
    model_prediction: dict[str, Any],
    historical_at_circuit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Returns a structured report dict (schema documented in README)."""
    predicted_bracket = model_prediction.get("bracket", 3)
    predicted_position = (BUCKET_RANGES.get(predicted_bracket, (10, 10)))[0]
    range_low, range_high = BUCKET_RANGES.get(predicted_bracket, (10, 12))

    confidence = float(model_prediction.get("confidence", 0.5))
    dnf_probability = float(model_prediction.get("dnf_probability", 0.06))

    strengths = [
        {
            "dimension": dim,
            "team_score": int(current_fingerprint.get(dim, 50)),
            "circuit_weight": float((compatibility.get("dimension_scores") or {}).get(dim, 0)) / 100,
        }
        for dim in compatibility.get("strengths_exploited", [])
    ]
    weaknesses = [
        {
            "dimension": dim,
            "team_score": int(current_fingerprint.get(dim, 50)),
            "circuit_weight": float((compatibility.get("dimension_scores") or {}).get(dim, 0)) / 100,
        }
        for dim in compatibility.get("weaknesses_exposed", [])
    ]

    upgrade_section: dict[str, Any] | None = None
    if last_upgrade:
        upgrade_section = {
            "last_upgrade_detected": {
                "race": last_upgrade.get("detected_at_race"),
                "affected_dimensions": last_upgrade.get("affected_dimensions"),
                "confidence": last_upgrade.get("confidence"),
                "notes": last_upgrade.get("notes"),
            },
            "upgrade_impact_at_this_circuit": upgrade_impact or {},
        }

    must_win = championship_position == 2 and championship_points_gap > 25 and races_remaining < 6
    pressure_level = (
        "Critical" if must_win else
        "High" if championship_points_gap > 50 else
        "Moderate" if championship_points_gap > 15 else
        "Low"
    )

    scenarios = _championship_scenarios(
        position=championship_position,
        gap=championship_points_gap,
        races_remaining=races_remaining,
    )

    return {
        "team": team_name,
        "team_code": team_code,
        "race": upcoming_race.get("name"),
        "round": upcoming_race.get("round"),
        "year": upcoming_race.get("year"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_compatibility": {
            "overall_score": compatibility.get("overall_score"),
            "verdict": compatibility.get("verdict"),
            "strengths_exploited": compatibility.get("strengths_exploited", []),
            "weaknesses_exposed": compatibility.get("weaknesses_exposed", []),
            "dimension_breakdown": compatibility.get("dimension_scores", {}),
        },
        "upgrade_analysis": upgrade_section,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "prediction": {
            "race": {
                "predicted_bracket": POSITION_BUCKET_LABELS[predicted_bracket],
                "predicted_position": predicted_position,
                "position_range": [range_low, range_high],
                "confidence": round(confidence, 3),
                "model_reasoning": _reasoning_for(predicted_bracket, compatibility),
            },
            "dnf_probability": round(dnf_probability, 3),
        },
        "championship_scenarios": {
            "current_position": championship_position,
            "points_gap_to_leader": championship_points_gap,
            "races_remaining": races_remaining,
            "scenarios": scenarios,
            "must_win_race": must_win,
            "pressure_level": pressure_level,
        },
        "historical_context": historical_at_circuit or {},
    }


def _championship_scenarios(position: int, gap: int, races_remaining: int) -> list[dict[str, Any]]:
    """Quick deterministic scenario table — what happens if the team wins / podiums / DNFs.
    The full distribution comes from championship_sim.py.
    """
    if position == 1:
        win = {"outcome": "Win", "points_gained": 25, "championship_gap_after": gap + 25 - 18, "title_probability_after": 0.65}
        podium = {"outcome": "Podium (P3)", "points_gained": 15, "championship_gap_after": gap + 15 - 25, "title_probability_after": 0.45}
        dnf = {"outcome": "DNF", "points_gained": 0, "championship_gap_after": gap - 25, "title_probability_after": 0.20}
    else:
        win = {
            "outcome": "Win + Fastest Lap",
            "points_gained": 26,
            "championship_gap_after": max(0, gap - 26),
            "title_probability_after": min(0.9, 0.4 + (0.05 * races_remaining)),
        }
        podium = {
            "outcome": "Podium (P3)",
            "points_gained": 15,
            "championship_gap_after": gap - 15 + 25,
            "title_probability_after": max(0.05, 0.25 - 0.02 * gap / 10),
        }
        dnf = {
            "outcome": "DNF",
            "points_gained": 0,
            "championship_gap_after": gap + 25,
            "title_probability_after": max(0.02, 0.10 - 0.01 * races_remaining),
        }
    return [win, podium, dnf]


def _reasoning_for(bracket: int, compatibility: dict[str, Any]) -> str:
    """Pre-baked one-liner per bracket — kept simple for explainability."""
    score = compatibility.get("overall_score", 50)
    if bracket == 0:
        return f"Compatibility {score}/100 — circuit rewards this team's strengths."
    if bracket == 1:
        return f"Strong fit ({score}/100); podium achievable barring strategy missteps."
    if bracket == 2:
        return "Mid-pack points expected; needs clean execution to gain places."
    if bracket == 3:
        return "Outside the points window — relies on rival attrition."
    return "Limited pace at this circuit; expecting a recovery drive at best."
