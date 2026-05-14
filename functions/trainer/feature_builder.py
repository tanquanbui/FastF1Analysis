"""Assemble the training CSV from DynamoDB.

For each (driver, race) row we need:
  * the team fingerprint as it stood BEFORE this race (no data leakage)
  * the circuit profile for the race's circuit
  * recent-form aggregates from prior races
  * championship context (position + gap)
  * the actual finishing position (the label)
"""
from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# Hard-coded mapping from race round → circuit key. In a real deployment this
# would come from a calendar table; for now we eyeball the 2024 season.
CALENDAR_CIRCUITS_2024: dict[int, str] = {
    1: "bahrain", 2: "jeddah", 3: "australia", 4: "japan", 5: "china",
    6: "miami", 7: "imola", 8: "monaco", 9: "canada", 10: "barcelona",
    11: "austria", 12: "silverstone", 13: "hungary", 14: "spa", 15: "zandvoort",
    16: "monza", 17: "baku", 18: "singapore", 19: "austin", 20: "mexico",
    21: "interlagos", 22: "las_vegas", 23: "qatar", 24: "abu_dhabi",
}


class FeatureBuilder:
    """Pulls items from DynamoDB and emits training rows.

    Kept as a class so we can inject a mocked table object in tests.
    """

    def __init__(self, table):
        self.table = table

    def build_training_set(self, years: list[int]) -> tuple[list[list[float]], list[int]]:
        """Return (feature_rows, labels) for every (driver, race) we have."""
        from features import TRAINING_FEATURES, position_to_bucket, build_feature_row
        from circuit_profiler import get_profile, compute_track_compatibility, FINGERPRINT_DIMENSIONS

        rows: list[list[float]] = []
        labels: list[int] = []

        for year in years:
            calendar = CALENDAR_CIRCUITS_2024  # placeholder; calendar varies year-on-year
            for round_number in sorted(calendar):
                results = self._query_pk(f"RACE#{year}#{round_number}", "RESULT#")
                if not results:
                    continue

                fingerprints = self._fingerprints_before(year, round_number)
                circuit_profile = get_profile(calendar[round_number]) or {}

                for r in results:
                    driver = r.get("DriverCode")
                    team = r.get("TeamCode")
                    position = self._as_int(r.get("Position"))
                    if not driver or not team or position is None:
                        continue

                    fp = fingerprints.get(team, {dim: 50 for dim in FINGERPRINT_DIMENSIONS})
                    compat = compute_track_compatibility(fp, circuit_profile)
                    recent_form = self._recent_form_for_driver(driver, year, round_number)
                    upgrade_ctx = self._upgrade_context(team, year, round_number)
                    championship_ctx = self._championship_context(team, year, round_number)

                    row = build_feature_row(
                        team_fingerprint=fp,
                        circuit_profile=circuit_profile,
                        track_compatibility=compat["overall_score"],
                        recent_form=recent_form,
                        championship_ctx=championship_ctx,
                        upgrade_ctx=upgrade_ctx,
                        session_ctx={"practice_pace_rank": position, "qualifying_position": self._as_int(r.get("Grid")) or 10},
                        weather_ctx={"rain_probability": 0.0, "expected_temperature": 25.0},
                    )

                    rows.append([row[name] for name in TRAINING_FEATURES])
                    labels.append(position_to_bucket(position))

        return rows, labels

    def to_csv(self, rows: list[list[float]], labels: list[int]) -> str:
        """Encode as XGBoost-style label-first CSV (no header)."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        for label, row in zip(labels, rows):
            writer.writerow([label, *row])
        return buf.getvalue()

    # ----- helpers -----

    def _query_pk(self, pk: str, sk_prefix: str) -> list[dict[str, Any]]:
        try:
            response = self.table.query(
                KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with(sk_prefix),
            )
            return response.get("Items", [])
        except Exception:
            logger.exception("query failed pk=%s", pk)
            return []

    def _fingerprints_before(self, year: int, round_number: int) -> dict[str, dict[str, float]]:
        """For each team, the latest fingerprint with Round < round_number."""
        from circuit_profiler import FINGERPRINT_DIMENSIONS

        latest: dict[str, tuple[int, dict[str, float]]] = {}
        # Scan would be expensive; instead query per team. We don't know the
        # team list here, so we fall through to scan with a filter.
        response = self.table.scan(
            FilterExpression=Key("Year").eq(year),
            ProjectionExpression="PK, SK, TeamCode, Round, " + ", ".join(FINGERPRINT_DIMENSIONS),
        )
        for item in response.get("Items", []):
            if not item.get("PK", "").startswith("FINGERPRINT#"):
                continue
            team = item.get("TeamCode")
            rnd = self._as_int(item.get("Round")) or 0
            if rnd >= round_number:
                continue
            current = latest.get(team)
            if current is None or current[0] < rnd:
                latest[team] = (
                    rnd,
                    {dim: float(item.get(dim, 50)) for dim in FINGERPRINT_DIMENSIONS},
                )
        return {team: fp for team, (_, fp) in latest.items()}

    def _recent_form_for_driver(self, driver: str, year: int, round_number: int) -> dict[str, float]:
        """Average finishing/qualifying position over the previous 3 rounds."""
        positions = []
        grids = []
        dnfs = 0
        total = 0
        for r in range(max(1, round_number - 3), round_number):
            results = self._query_pk(f"RACE#{year}#{r}", f"RESULT#{driver}")
            for item in results:
                if item.get("DriverCode") != driver:
                    continue
                total += 1
                pos = self._as_int(item.get("Position"))
                grid = self._as_int(item.get("Grid"))
                if pos is not None:
                    positions.append(pos)
                else:
                    dnfs += 1
                if grid is not None:
                    grids.append(grid)

        return {
            "avg_finishing_position_l3": sum(positions) / len(positions) if positions else 10,
            "avg_qualifying_position_l3": sum(grids) / len(grids) if grids else 10,
            "dnf_rate_l10": dnfs / total if total else 0.0,
        }

    def _upgrade_context(self, team: str, year: int, round_number: int) -> dict[str, float]:
        upgrades = self._query_pk(f"UPGRADE#{year}#{team}", "RACE#")
        max_delta = 0.0
        last_upgrade_round = -100
        for u in upgrades:
            rnd = self._as_int(u.get("Round")) or 0
            if rnd >= round_number:
                continue
            last_upgrade_round = max(last_upgrade_round, rnd)
            delta_map = u.get("Delta") or {}
            for value in delta_map.values():
                try:
                    max_delta = max(max_delta, float(value))
                except (TypeError, ValueError):
                    continue
        return {
            "races_since_last_upgrade": float(round_number - last_upgrade_round) if last_upgrade_round > 0 else 99.0,
            "upgrade_dimension_delta_max": max_delta,
        }

    def _championship_context(self, team: str, year: int, round_number: int) -> dict[str, float]:
        if round_number <= 1:
            return {"position": 5, "points_gap_to_leader": 0, "races_remaining": 24, "must_win_pressure": 0}
        prior_round = round_number - 1
        standings = self._query_pk(f"STANDINGS#{year}#{prior_round}", f"CONSTRUCTOR#{team}")
        position = 10
        points_gap = 0
        for s in standings:
            position = self._as_int(s.get("Position")) or 10
            # gap to leader requires looking at constructor #1 — derive below
        # Need leader's points for gap calculation
        all_constructors = self._query_pk(f"STANDINGS#{year}#{prior_round}", "CONSTRUCTOR#")
        leader_points = 0
        team_points = 0
        for s in all_constructors:
            pts = float(s.get("Points") or 0)
            if (self._as_int(s.get("Position")) or 0) == 1:
                leader_points = pts
            if s.get("TeamCode") == team:
                team_points = pts
        points_gap = max(0, leader_points - team_points)

        races_total = max(CALENDAR_CIRCUITS_2024)
        races_remaining = max(0, races_total - round_number)
        must_win = 1.0 if (points_gap > 25 and races_remaining < 6) else 0.0
        return {
            "position": position,
            "points_gap_to_leader": points_gap,
            "races_remaining": races_remaining,
            "must_win_pressure": must_win,
        }

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
