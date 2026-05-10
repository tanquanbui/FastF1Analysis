"""Local smoke test — invokes ingestion handler with a single race + mock S3.

Usage:
    python scripts/local_test.py 2024 5
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("year", type=int)
    parser.add_argument("round", type=int)
    parser.add_argument("--sessions", default="R,Q")
    args = parser.parse_args()

    fn_dir = Path(__file__).parent.parent / "functions" / "ingestion"
    sys.path.insert(0, str(fn_dir))
    os.environ.setdefault("RAW_BUCKET", "local-test-bucket")
    os.environ.setdefault("FASTF1_CACHE_DIR", str(Path.cwd() / "fastf1_cache"))

    import app

    s3_writes = []

    def fake_put_object(**kwargs):
        s3_writes.append({"Key": kwargs["Key"], "size_bytes": len(kwargs["Body"])})

    s3_mock = MagicMock()
    s3_mock.put_object.side_effect = fake_put_object

    event = {
        "year": args.year,
        "round": args.round,
        "session_types": [s.strip() for s in args.sessions.split(",")],
    }

    with patch.object(app, "s3", s3_mock):
        result = app.handler(event, MagicMock())

    print("--- handler result ---")
    print(result)
    print("--- S3 writes (mocked) ---")
    for w in s3_writes:
        print(f"  {w['Key']}  ({w['size_bytes']} bytes)")
    return 0 if result.get("statusCode") == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
