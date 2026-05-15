"""Championship Monte Carlo simulator.

Given the current standings, the remaining race calendar, and a per-team
finishing-position probability distribution at each remaining race, simulate
the rest of the season ``n`` times and report:

  * title probability per driver / per constructor
  * the earliest race the leader can mathematically clinch
  * scenarios requiring a specific outcome combo to overtake
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# F1 points per position (post-2010 system; ignores fastest-lap bonus)
POINTS_PER_POSITION = {
    1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1,
}

# Default position-probability vector when the model has no info on a team.
# Weighted to mid-field finishing.
DEFAULT_POS_PROBS = {p: 1 / 20 for p in range(1, 21)}


def simulate_championship(
    current_standings: dict[str, Any],
    remaining_races: list[dict[str, Any]],
    position_distributions: dict[str, dict[int, float]],
    n_simulations: int = 10000,
    seed: int = 42,
) -> dict[str, Any]:
    """Run ``n_simulations`` end-of-season simulations.

    ``current_standings`` schema:
        {
          "drivers": [{"driver_code": "VER", "team_code": "RBR", "points": 250}, ...],
          "constructors": [{"team_code": "RBR", "points": 450}, ...],
        }

    ``position_distributions``:
        {"VER": {1: 0.6, 2: 0.2, 3: 0.1, ...}, "NOR": {...}, ...}
    """
    if not remaining_races or not current_standings.get("drivers"):
        return {"title_probabilities": {}, "constructor_title_probabilities": {}}

    rng = np.random.default_rng(seed)
    drivers = current_standings["drivers"]
    constructors = current_standings.get("constructors", [])
    driver_to_team = {d["driver_code"]: d.get("team_code") for d in drivers}

    title_counts: dict[str, int] = defaultdict(int)
    constructor_counts: dict[str, int] = defaultdict(int)
    points_distribution: dict[str, list[float]] = defaultdict(list)

    for _ in range(n_simulations):
        # Driver points carried forward
        driver_points = {d["driver_code"]: float(d["points"]) for d in drivers}
        team_points = {c["team_code"]: float(c["points"]) for c in constructors}

        for _ in remaining_races:
            for driver_code in driver_points:
                pos = _sample_position(
                    position_distributions.get(driver_code, DEFAULT_POS_PROBS),
                    rng,
                )
                pts = POINTS_PER_POSITION.get(pos, 0)
                driver_points[driver_code] += pts
                team = driver_to_team.get(driver_code)
                if team:
                    team_points[team] = team_points.get(team, 0) + pts

        title_winner = max(driver_points, key=driver_points.get)
        title_counts[title_winner] += 1
        if team_points:
            const_winner = max(team_points, key=team_points.get)
            constructor_counts[const_winner] += 1
        for code, pts in driver_points.items():
            points_distribution[code].append(pts)

    title_probs = {code: count / n_simulations for code, count in title_counts.items()}
    constructor_probs = {code: count / n_simulations for code, count in constructor_counts.items()}

    # Earliest mathematical clinch round per driver
    clinch = _compute_clinch_rounds(drivers, remaining_races, position_distributions, rng)

    return {
        "title_probabilities": dict(sorted(title_probs.items(), key=lambda kv: -kv[1])),
        "constructor_title_probabilities": dict(sorted(constructor_probs.items(), key=lambda kv: -kv[1])),
        "expected_points": {
            code: round(float(np.mean(p)), 1) for code, p in points_distribution.items()
        },
        "championship_clinch_probabilities": clinch,
        "simulations": n_simulations,
    }


def _sample_position(probs: dict[int, float], rng: np.random.Generator) -> int:
    """Sample a finishing position from a discrete probability vector."""
    positions, weights = zip(*probs.items())
    total = sum(weights)
    normalised = [w / total for w in weights]
    return int(rng.choice(positions, p=normalised))


def _compute_clinch_rounds(
    drivers: list[dict[str, Any]],
    remaining_races: list[dict[str, Any]],
    distributions: dict[str, dict[int, float]],
    rng: np.random.Generator,
    samples: int = 500,
) -> dict[str, dict[str, float]]:
    """Lightweight per-race clinch probability for the top-2 contenders only.

    For each remaining race, fraction of sims where the leader's max-possible
    additional points cannot be overtaken by P2.
    """
    if len(drivers) < 2:
        return {}

    leader = drivers[0]["driver_code"]
    contenders = [d["driver_code"] for d in drivers[:4]]
    clinch: dict[str, dict[str, float]] = {leader: {}}
    max_remaining_per_race = 26  # win + fastest lap

    for race_idx, race in enumerate(remaining_races):
        races_left_after = len(remaining_races) - race_idx - 1
        clinches = 0
        for _ in range(samples):
            leader_pts = drivers[0]["points"]
            best_rival = 0
            for d in drivers[1:4]:
                rival_pts = d["points"]
                # Sample one race for each contender
                pos_leader = _sample_position(distributions.get(leader, DEFAULT_POS_PROBS), rng)
                pos_rival = _sample_position(distributions.get(d["driver_code"], DEFAULT_POS_PROBS), rng)
                leader_pts += POINTS_PER_POSITION.get(pos_leader, 0)
                rival_pts += POINTS_PER_POSITION.get(pos_rival, 0)
                best_rival = max(best_rival, rival_pts)
            # If gap > max points the rival can still score over the rest of the season → clinched.
            if leader_pts - best_rival > races_left_after * max_remaining_per_race:
                clinches += 1
        clinch[leader][race.get("name") or f"round_{race_idx + 1}"] = round(clinches / samples, 3)
    return clinch
