"""Circuit analysis routes — team × circuit compatibility breakdowns.

Uses the ``circuit_profiler`` module from the shared Lambda Layer
(``/opt/python/`` in Lambda, ``shared/python/`` for local tests).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import route
from circuit_profiler import (
    FINGERPRINT_DIMENSIONS,
    compute_track_compatibility,
    get_profile,
)

from ._common import query_by_pk

KNOWN_TEAM_CODES = ["RBR", "MCL", "FER", "MER", "AST", "ALP", "WIL", "RB", "SAU", "HAA"]


@route("/team/{code}/circuit/{circuit_key}")
def get_team_circuit_compatibility(code: str, circuit_key: str, event: dict[str, Any]) -> dict[str, Any]:
    code = code.upper()
    year = (event.get("queryStringParameters") or {}).get("year") or datetime.now(timezone.utc).year
    profile = get_profile(circuit_key)
    if profile is None:
        raise KeyError(f"unknown circuit {circuit_key}")

    items = query_by_pk(f"FINGERPRINT#{year}#{code}", sk_prefix="TRACK#")
    if not items:
        raise KeyError(f"no fingerprints for {code} in {year}")
    latest = max(items, key=lambda i: int(i.get("Round") or 0))
    fingerprint = {dim: float(latest.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS}

    compat = compute_track_compatibility(fingerprint, profile)
    return {
        "team_code": code,
        "circuit": {
            "key": circuit_key,
            "weights": {k: profile[k] for k in FINGERPRINT_DIMENSIONS if k in profile},
            "notes": profile.get("notes"),
        },
        "fingerprint": fingerprint,
        "compatibility": compat,
    }


@route("/circuit/{circuit_key}/teams")
def get_circuit_team_ranking(circuit_key: str, event: dict[str, Any]) -> dict[str, Any]:
    profile = get_profile(circuit_key)
    if profile is None:
        raise KeyError(f"unknown circuit {circuit_key}")
    year = (event.get("queryStringParameters") or {}).get("year") or datetime.now(timezone.utc).year

    ranked = []
    for code in KNOWN_TEAM_CODES:
        items = query_by_pk(f"FINGERPRINT#{year}#{code}", sk_prefix="TRACK#")
        if not items:
            continue
        latest = max(items, key=lambda i: int(i.get("Round") or 0))
        fingerprint = {dim: float(latest.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS}
        compat = compute_track_compatibility(fingerprint, profile)
        ranked.append(
            {
                "team_code": code,
                "compatibility_score": compat["overall_score"],
                "verdict": compat["verdict"],
                "strengths_exploited": compat["strengths_exploited"],
                "weaknesses_exposed": compat["weaknesses_exposed"],
            }
        )

    ranked.sort(key=lambda t: -t["compatibility_score"])
    return {
        "circuit_key": circuit_key,
        "circuit_name": circuit_key.replace("_", " ").title(),
        "notes": profile.get("notes"),
        "teams": ranked,
    }
