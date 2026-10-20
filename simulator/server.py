"""Local simulator server: JSON API under /api plus the dashboard as static files.

    python -m simulator.server                # http://localhost:8080
    python -m simulator.server --demo         # force offline demo mode (no API key needed)

Routes:
    GET  /api/status
    GET  /api/calendar/{year}
    GET  /api/context/{year}/{round}?source=auto
    POST /api/simulate          {year, round, source?, scenario?, runs?, demo?}
    POST /api/whatif            {session_id, question}
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .circuits import list_calendar
from .context import RaceContext, build_context
from .demo import demo_simulation
from .engine import DEFAULT_EFFORT, DEFAULT_MODEL, RaceSimulator, SimulationError, SimulationResult, Usage
from . import validate

logger = logging.getLogger(__name__)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_RUNS = 10


class _Api:
    def __init__(self, demo: bool):
        self.force_demo = demo
        self.sessions: dict[str, Any] = {}
        self.contexts: dict[tuple, RaceContext] = {}
        self.lock = threading.Lock()
        self._simulator: RaceSimulator | None = None

    @property
    def ai_available(self) -> bool:
        return not self.force_demo and bool(
            os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )

    @property
    def simulator(self) -> RaceSimulator:
        if self._simulator is None:
            self._simulator = RaceSimulator()
        return self._simulator

    def context(self, year: int, round_number: int, source: str) -> RaceContext:
        key = (year, round_number, source)
        with self.lock:
            cached = self.contexts.get(key)
        if cached is None:
            cached = build_context(year, round_number, source=source)  # FastF1 loads can be slow
            with self.lock:
                self.contexts[key] = cached
        return cached

    def status(self) -> dict[str, Any]:
        return {
            "ai_available": self.ai_available,
            "mode": "ai" if self.ai_available else "demo",
            "model": DEFAULT_MODEL,
            "effort": DEFAULT_EFFORT,
        }

    def simulate(self, body: dict[str, Any]) -> dict[str, Any]:
        year, rnd = int(body["year"]), int(body["round"])
        scenario = (body.get("scenario") or "").strip() or None
        runs = max(1, min(int(body.get("runs") or 1), MAX_RUNS))
        ctx = self.context(year, rnd, body.get("source") or "auto")
        payload: dict[str, Any] = {"context": _context_json(ctx)}

        if body.get("demo") or not self.ai_available:
            result = _demo_result(ctx, scenario)
            payload.update(mode="demo", result=result.model_dump(mode="json"))
            return payload

        if runs > 1:
            summary = self.simulator.simulate_many(ctx, scenario, runs=runs)
            payload.update(mode="ai", monte_carlo=summary.model_dump(mode="json", exclude={"results"}))
            payload["result"] = summary.results[0].model_dump(mode="json")
            payload["runs"] = [r.model_dump(mode="json") for r in summary.results]
            return payload

        session = self.simulator.start(ctx)
        result = session.run(scenario)
        with self.lock:
            self.sessions[session.id] = session
        payload.update(mode="ai", result=result.model_dump(mode="json"))
        return payload

    def what_if(self, body: dict[str, Any]) -> dict[str, Any]:
        question = (body.get("question") or "").strip()
        if not question:
            raise ValueError("question is required")
        with self.lock:
            session = self.sessions.get(body.get("session_id", ""))
        if session is None:
            raise LookupError("unknown session - run a simulation first (demo runs don't support what-ifs)")
        return {"mode": "ai", "result": session.what_if(question).model_dump(mode="json")}


def _context_json(ctx: RaceContext) -> dict[str, Any]:
    data = ctx.model_dump(mode="json")
    data["has_actual_result"] = bool(ctx.actual_result)
    return data


def _demo_result(ctx: RaceContext, scenario: str | None) -> SimulationResult:
    sim = demo_simulation(ctx, scenario)
    return SimulationResult(
        id="demo", session_id="demo", kind="run", prompt=scenario, model="demo (offline pace model)",
        simulation=sim, points=validate.points_for(sim, ctx.year), issues=validate.check(sim, ctx),
        comparison=validate.compare_to_actual(sim, ctx.actual_result), usage=Usage(),
    )


def _make_handler(api: _Api):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: Any, content_type: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if not parts or parts[0] != "api":
                return self._static(url.path) if method == "GET" else self._send(404, {"error": "not found"})
            try:
                if method == "GET" and parts[1:] == ["status"]:
                    return self._send(200, api.status())
                if method == "GET" and len(parts) == 3 and parts[1] == "calendar":
                    return self._send(200, list_calendar(int(parts[2])))
                if method == "GET" and len(parts) == 4 and parts[1] == "context":
                    source = parse_qs(url.query).get("source", ["auto"])[0]
                    ctx = api.context(int(parts[2]), int(parts[3]), source)
                    return self._send(200, {**_context_json(ctx), "prompt": ctx.to_prompt()})
                if method == "POST" and parts[1:] in (["simulate"], ["whatif"]):
                    length = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(length) or b"{}")
                    handler = api.simulate if parts[1] == "simulate" else api.what_if
                    return self._send(200, handler(body))
                return self._send(404, {"error": "not found"})
            except LookupError as exc:
                return self._send(404, {"error": str(exc)})
            except (ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})
            except SimulationError as exc:
                return self._send(502, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.exception("request failed")
                return self._send(500, {"error": f"server error: {exc}"})

        def _static(self, path: str) -> None:
            target = (FRONTEND / (path.lstrip("/") or "index.html")).resolve()
            if not target.is_relative_to(FRONTEND) or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(200, target.read_bytes(), ctype)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def log_message(self, fmt, *args):
            logger.info("%s %s", self.command, self.path)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI race simulator - local server")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--demo", action="store_true", help="never call Claude; use the offline demo model")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    api = _Api(demo=args.demo)
    server = ThreadingHTTPServer((args.host, args.port), _make_handler(api))
    mode = "AI (" + DEFAULT_MODEL + ")" if api.ai_available else "DEMO - set ANTHROPIC_API_KEY for AI simulations"
    print(f"\n  Race simulator on http://{args.host}:{args.port}  [{mode}]\n  Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
