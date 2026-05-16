"""Local API dev server — bypasses SAM/Docker entirely.

Imports the API Lambda's ``app.handler`` directly and exposes it on
``localhost:3000`` via Python's built-in http.server. Useful when you want to
see the dashboard render against the real API code without provisioning AWS.

Modes:
  --mock      Serve canned fixtures from scripts/mock_fixtures/ — no AWS needed.
  (default)   Pass-through to real DynamoDB. Requires AWS credentials and
              TABLE_NAME env var pointing at a real table.

Usage:
  python scripts/local_api.py --mock
  python scripts/local_api.py                 # uses real DynamoDB
  python scripts/local_api.py --port 3001     # custom port
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "scripts" / "mock_fixtures"


def _load_handler(mock: bool):
    """Wire up sys.path + env vars, then import the API handler."""
    sys.path.insert(0, str(ROOT / "functions" / "api"))
    sys.path.insert(0, str(ROOT / "shared" / "python"))

    os.environ.setdefault("TABLE_NAME", "F1Data-local")
    os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
    # Stop boto3 from looking up real creds when we're in mock mode
    if mock:
        os.environ["AWS_ACCESS_KEY_ID"] = "mock"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "mock"

    import app  # type: ignore  # noqa: E402

    if mock:
        from routes import _common  # type: ignore  # noqa: E402
        _common.table = _MockTable()
    return app.handler


class _MockTable:
    """Mimics the subset of boto3.dynamodb.Table the API actually uses.

    Each fixture file under scripts/mock_fixtures/ maps a PK pattern to a
    list of items. Query returns items whose PK matches.
    """

    def __init__(self):
        self._by_pk: dict[str, list[dict]] = {}
        if FIXTURES.exists():
            for fp in FIXTURES.glob("*.json"):
                with fp.open() as f:
                    payload = json.load(f)
                for item in payload:
                    self._by_pk.setdefault(item["PK"], []).append(item)
            logger.info("mock loaded %d PKs from %s", len(self._by_pk), FIXTURES)
        else:
            logger.warning("no mock_fixtures/ directory — every query will be empty")

    @staticmethod
    def _parse_condition(cond):
        """Walk a boto3 KeyConditionExpression to extract (pk, sk_prefix).

        Handles three shapes:
            Key('PK').eq(x)
            Key('PK').eq(x) & Key('SK').begins_with(y)
            Key('SomeAttr').eq(x)   # GSI partition key
        """
        if cond is None:
            return None, None

        def _walk(node, found):
            # boto3.dynamodb.conditions: ConditionBase has .get_expression()
            # returning {"format": "...", "operator": ..., "values": (...)}.
            expr = getattr(node, "get_expression", None)
            if expr is None:
                return
            data = node.get_expression() if callable(expr) else expr
            op = data.get("operator") if isinstance(data, dict) else None
            values = data.get("values") if isinstance(data, dict) else None

            if op == "AND":
                for sub in values or []:
                    _walk(sub, found)
            elif op == "=" and values and len(values) >= 2:
                # values[0] is the Attr/Key path object, values[1] is the constant
                found.setdefault("pk", values[1])
            elif op == "begins_with" and values and len(values) >= 2:
                found.setdefault("sk_prefix", values[1])

        found: dict = {}
        _walk(cond, found)
        return found.get("pk"), found.get("sk_prefix")

    def query(self, **kwargs):
        cond = kwargs.get("KeyConditionExpression")
        pk, sk_prefix = self._parse_condition(cond)

        items = self._by_pk.get(pk, [])
        if sk_prefix:
            items = [i for i in items if str(i.get("SK", "")).startswith(sk_prefix)]
        # GSI shortcut: also match if any item.PK*-like field equals pk (used
        # for DriverRaceIndex / TeamTrackIndex queries).
        if kwargs.get("IndexName") and not items:
            for bucket in self._by_pk.values():
                for item in bucket:
                    if kwargs["IndexName"] == "DriverRaceIndex" and item.get("DriverCode") == pk:
                        items.append(item)
                    elif kwargs["IndexName"] == "TeamTrackIndex" and item.get("TeamCode") == pk:
                        items.append(item)
        return {"Items": items}


def _make_request_handler(handler_fn):
    class _Handler(BaseHTTPRequestHandler):
        def _handle(self, method: str):
            parsed = urlparse(self.path)
            event = {
                "path": parsed.path,
                "httpMethod": method,
                "queryStringParameters": dict(
                    pair.split("=", 1) if "=" in pair else (pair, "")
                    for pair in parsed.query.split("&")
                    if pair
                ),
                "requestContext": {},
            }
            try:
                response = handler_fn(event, None)
            except Exception:
                logger.exception("handler error")
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"error":"local handler crashed"}')
                return

            self.send_response(response.get("statusCode", 200))
            for header, value in (response.get("headers") or {}).items():
                self.send_header(header, value)
            if "Access-Control-Allow-Origin" not in (response.get("headers") or {}):
                self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            body = response.get("body", "")
            if isinstance(body, str):
                self.wfile.write(body.encode())
            else:
                self.wfile.write(json.dumps(body).encode())

        def do_GET(self):
            self._handle("GET")

        def do_OPTIONS(self):
            self._handle("OPTIONS")

        def log_message(self, format, *args):
            logger.info("%s %s", self.command, self.path)

    return _Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--mock", action="store_true", help="serve canned fixtures, no AWS")
    args = parser.parse_args()

    handler_fn = _load_handler(mock=args.mock)
    request_handler = _make_request_handler(handler_fn)

    server = ThreadingHTTPServer(("localhost", args.port), request_handler)
    mode = "mock" if args.mock else "live DynamoDB"
    print(f"\n  PitStop API ({mode}) listening on http://localhost:{args.port}")
    print(f"  Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
