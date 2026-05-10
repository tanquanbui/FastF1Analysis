"""Backfill historical races by invoking the ingestion Lambda once per round.

Usage:
    python scripts/seed_historical.py --start 2020 --end 2024
    python scripts/seed_historical.py --start 2024 --end 2024 --rounds 1-5
    python scripts/seed_historical.py --local   # call the ingestion app.handler
                                                # directly without going via Lambda

By default seeds 2020 → 2024 across the full calendar. Paces requests to avoid
hammering the FastF1/Ergast upstream — adds a 2s sleep between rounds.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _import_local_handler():
    """Add functions/ingestion to sys.path and import the handler directly."""
    fn_dir = Path(__file__).parent.parent / "functions" / "ingestion"
    sys.path.insert(0, str(fn_dir))
    os.environ.setdefault("RAW_BUCKET", os.environ.get("BACKFILL_RAW_BUCKET", "pitstop-raw-local"))
    os.environ.setdefault("FASTF1_CACHE_DIR", str(Path.cwd() / "fastf1_cache"))
    import app
    return app.handler


def _resolve_function_name(stack: str = "pitstop-analytics") -> str:
    """Look up the Lambda function name via CloudFormation."""
    import boto3
    cf = boto3.client("cloudformation")
    resources = cf.list_stack_resources(StackName=stack)["StackResourceSummaries"]
    for r in resources:
        if r["ResourceType"] == "AWS::Lambda::Function" and "Ingestion" in r["LogicalResourceId"]:
            return r["PhysicalResourceId"]
    raise RuntimeError(f"no IngestionFunction in stack {stack}")


def _invoke_lambda(function_name: str, payload: dict) -> dict:
    import boto3
    lam = boto3.client("lambda")
    response = lam.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    body = json.loads(response["Payload"].read().decode("utf-8"))
    if response.get("FunctionError"):
        raise RuntimeError(f"lambda error: {body}")
    return body


def _race_calendar(year: int) -> list[int]:
    """Return list of round numbers for a season via the Ergast mirror."""
    import requests
    url = f"https://api.jolpi.ca/ergast/f1/{year}.json?limit=100"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    races = response.json()["MRData"]["RaceTable"]["Races"]
    return sorted(int(r["round"]) for r in races)


def _parse_rounds(spec: str | None, calendar: list[int]) -> list[int]:
    if not spec:
        return calendar
    rounds = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            a, b = chunk.split("-")
            rounds.update(range(int(a), int(b) + 1))
        elif chunk:
            rounds.add(int(chunk))
    return sorted(r for r in calendar if r in rounds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2020)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument("--rounds", type=str, default=None, help="round filter: '1-5' or '1,3,5'")
    parser.add_argument(
        "--sessions",
        type=str,
        default="R,Q",
        help="comma-separated FastF1 session types (R, Q, S, FP3...)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="invoke ingestion handler directly instead of via Lambda",
    )
    parser.add_argument("--stack", type=str, default="pitstop-analytics")
    parser.add_argument("--sleep", type=float, default=2.0, help="seconds to wait between rounds")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sessions = [s.strip() for s in args.sessions.split(",") if s.strip()]
    handler = None
    function_name = None
    if args.local:
        handler = _import_local_handler()
    else:
        function_name = _resolve_function_name(args.stack)
        logger.info("invoking %s for backfill", function_name)

    failures = []
    for year in range(args.start, args.end + 1):
        try:
            calendar = _race_calendar(year)
        except Exception as exc:
            logger.error("failed to fetch %s calendar: %s", year, exc)
            failures.append((year, None, str(exc)))
            continue

        targets = _parse_rounds(args.rounds, calendar)
        logger.info("%s: %d rounds queued", year, len(targets))

        for round_number in targets:
            payload = {"year": year, "round": round_number, "session_types": sessions}
            logger.info("→ %s round %s sessions=%s", year, round_number, sessions)
            if args.dry_run:
                continue
            try:
                if args.local:
                    handler(payload, None)
                else:
                    _invoke_lambda(function_name, payload)
            except Exception as exc:
                logger.exception("failed for %s-%s", year, round_number)
                failures.append((year, round_number, str(exc)))
            time.sleep(args.sleep)

    if failures:
        logger.warning("%d failures:", len(failures))
        for year, rnd, err in failures:
            logger.warning("  %s round=%s: %s", year, rnd, err[:200])
        return 1
    logger.info("backfill complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
