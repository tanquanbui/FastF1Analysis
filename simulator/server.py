"""Local simulator app: JSON API under /api plus the dashboard as static files.

    python -m simulator.server                # http://localhost:8080
    python -m simulator.server --demo         # never call Claude (offline demo model)

Long work (loading a FastF1 weekend, simulating) runs as background jobs:
POST returns a job id; poll GET /api/jobs/{id} for stage, live reasoning and
progress. Finished simulations are saved to data/simulator.db.

Routes:
    GET    /api/status
    GET    /api/seasons
    GET    /api/calendar/{year}
    GET    /api/context/{year}/{round}?source=      cached race context (404 if not loaded)
    POST   /api/prepare      {year, round, source, refresh?}              -> job
    POST   /api/simulate     {year, round, source, scenario?, runs?}      -> job
    POST   /api/whatif       {session_id, question}                       -> job
    GET    /api/jobs/{id}
    GET    /api/history
    GET    /api/results/{id}
    DELETE /api/results/{id}
    GET    /api/results/{id}/export.md | export.json
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import validate
from .circuits import CALENDARS, list_calendar
from .context import RaceContext, build_context
from .demo import demo_simulation
from .engine import DEFAULT_EFFORT, DEFAULT_MODEL, RaceSimulator, SimulationResult, SimulationSession, Usage
from .export import to_markdown
from .store import ContextCache, History

logger = logging.getLogger(__name__)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_RUNS = 10
FIRST_SEASON = 2018  # FastF1 timing data starts here


class Job:
    def __init__(self, kind: str, label: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.label = label
        self.state = "queued"
        self.started_at = time.time()
        self.info: dict[str, Any] = {"stage": "Queued"}
        self.output: dict[str, Any] | None = None
        self.error: str | None = None

    def update(self, event: dict[str, Any]) -> None:
        self.info.update(event)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "label": self.label, "state": self.state,
            "elapsed_s": round(time.time() - self.started_at, 1), **self.info,
            "output": self.output, "error": self.error,
        }


class App:
    def __init__(self, demo: bool):
        self.force_demo = demo
        self.cache = ContextCache()
        self.history = History()
        self.jobs: dict[str, Job] = {}
        self.sessions: dict[str, SimulationSession] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="sim-job")
        self._simulator: RaceSimulator | None = None

    # ---- basics
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

    def status(self) -> dict[str, Any]:
        try:
            import fastf1  # noqa: F401

            fastf1_ok = True
        except ImportError:
            fastf1_ok = False
        return {
            "ai_available": self.ai_available,
            "mode": "ai" if self.ai_available else "demo",
            "model": DEFAULT_MODEL,
            "effort": DEFAULT_EFFORT,
            "fastf1_installed": fastf1_ok,
        }

    def seasons(self) -> list[int]:
        return list(range(max(CALENDARS), FIRST_SEASON - 1, -1))

    def calendar(self, year: int) -> list[dict[str, Any]]:
        races = list_calendar(year)
        if not races:
            races = _fastf1_calendar(year)
        cached = self.cache.cached_rounds(year)
        for r in races:
            r["cached_sources"] = sorted(cached.get(r["round"], []))
        return races

    # ---- jobs
    def submit(self, kind: str, label: str, fn: Callable[[Job], dict[str, Any]]) -> dict[str, Any]:
        job = Job(kind, label)
        with self.lock:
            self.jobs[job.id] = job

        def run() -> None:
            job.state = "running"
            try:
                job.output = fn(job)
                job.state = "done"
                job.update({"stage": "Done"})
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                logger.exception("job %s failed", job.id)
                job.state = "error"
                job.error = str(exc)

        self.pool.submit(run)
        return job.to_json()

    def job(self, job_id: str) -> dict[str, Any]:
        job = self.jobs.get(job_id)
        if job is None:
            raise LookupError("unknown job")
        return job.to_json()

    # ---- context
    def get_context(self, year: int, rnd: int, source: str, job: Job | None = None,
                    refresh: bool = False) -> RaceContext:
        if not refresh:
            cached = self.cache.get(year, rnd, source)
            if cached is not None:
                return cached
        progress = (lambda msg: job.update({"stage": msg})) if job else None
        ctx = build_context(year, rnd, source=source, progress=progress)
        self.cache.put(ctx, source)
        return ctx

    def prepare(self, body: dict[str, Any]) -> dict[str, Any]:
        year, rnd, source = int(body["year"]), int(body["round"]), body.get("source") or "auto"

        def work(job: Job) -> dict[str, Any]:
            job.update({"stage": "Loading race data"})
            ctx = self.get_context(year, rnd, source, job, refresh=bool(body.get("refresh")))
            return {"year": year, "round": rnd, "source": source, "tables": len(ctx.tables),
                    "drivers": len(ctx.drivers)}

        return self.submit("prepare", f"Load {year} R{rnd} data", work)

    # ---- simulation
    def simulate(self, body: dict[str, Any]) -> dict[str, Any]:
        year, rnd = int(body["year"]), int(body["round"])
        source = body.get("source") or "auto"
        scenario = (body.get("scenario") or "").strip() or None
        runs = max(1, min(int(body.get("runs") or 1), MAX_RUNS))
        demo = bool(body.get("demo")) or not self.ai_available

        def work(job: Job) -> dict[str, Any]:
            job.update({"stage": "Loading race data"})
            ctx = self.get_context(year, rnd, source, job)
            if demo:
                session = SimulationSession(None, ctx)
                result = _demo_result(ctx, scenario, session.id)
                self.history.save_session(session, source, model=result.model)
                self.history.save_result(result, "demo")
                return {"result_id": result.id, "session_id": session.id}
            if runs == 1:
                session = self.simulator.start(ctx)
                result = session.run(scenario, progress=job.update)
                self._remember(session, source)
                self.history.save_result(result, "ai")
                return {"result_id": result.id, "session_id": session.id}

            batch_id = uuid.uuid4().hex[:12]
            summary = self.simulator.simulate_many(
                ctx, scenario, runs=runs, progress=job.update,
                on_session=lambda s: self._remember(s, source),
            )
            for r in summary.results:
                self.history.save_result(r, "ai", batch_id=batch_id)
            self.history.save_batch(batch_id, summary.model_dump(mode="json", exclude={"results"}))
            first = summary.results[0]
            return {"result_id": first.id, "session_id": first.session_id, "batch_id": batch_id}

        label = f"{year} R{rnd}" + (f" · {scenario}" if scenario else "") + (f" × {runs}" if runs > 1 else "")
        return self.submit("simulate", label, work)

    def what_if(self, body: dict[str, Any]) -> dict[str, Any]:
        question = (body.get("question") or "").strip()
        session_id = body.get("session_id") or ""
        if not question:
            raise ValueError("question is required")
        if not self.ai_available:
            raise ValueError("what-ifs need AI mode (set ANTHROPIC_API_KEY)")
        session = self._session(session_id)

        def work(job: Job) -> dict[str, Any]:
            result = session.what_if(question, progress=job.update)
            self._remember(session, None)
            self.history.save_result(result, "ai")
            return {"result_id": result.id, "session_id": session.id}

        return self.submit("whatif", question, work)

    def _remember(self, session: SimulationSession, source: str | None) -> None:
        with self.lock:
            self.sessions[session.id] = session
        stored = self.history.load_session(session.id)
        self.history.save_session(session, source or (stored[2] if stored else "auto"))

    def _session(self, session_id: str) -> SimulationSession:
        with self.lock:
            session = self.sessions.get(session_id)
        if session is not None:
            return session
        stored = self.history.load_session(session_id)
        if stored is None:
            raise LookupError("unknown session")
        ctx, messages, _ = stored
        if not messages:
            raise ValueError("this simulation was a demo run, so it can't take what-ifs")
        session = self.simulator.resume(session_id, ctx, messages)
        with self.lock:
            self.sessions[session_id] = session
        return session

    # ---- history
    def result(self, result_id: str) -> dict[str, Any]:
        row = self.history.get_result(result_id)
        if row is None:
            raise LookupError("unknown result")
        stored = self.history.load_session(row["session_id"])
        ctx = stored[0] if stored else None
        siblings = [
            {"id": r["id"], "kind": r["kind"], "prompt": r["prompt"], "headline": r["headline"]}
            for r in self.history.session_results(row["session_id"])
        ]
        return {
            **row,
            "context": _context_json(ctx) if ctx else None,
            "versions": siblings,
            "batch": self.history.get_batch(row["batch_id"]) if row.get("batch_id") else None,
            "batch_runs": self.history.batch_result_ids(row["batch_id"]) if row.get("batch_id") else [],
            "can_what_if": bool(stored and stored[1]) and self.ai_available,
        }


def _fastf1_calendar(year: int) -> list[dict[str, Any]]:
    from .circuits import circuit_key_for_location, event_name

    try:
        from .fastf1_source import _fastf1

        schedule = _fastf1().get_event_schedule(year, include_testing=False)
    except Exception as exc:  # noqa: BLE001
        logger.info("no schedule for %s: %s", year, exc)
        return []
    races = []
    for _, row in schedule.iterrows():
        key = circuit_key_for_location(str(row["Location"]))
        races.append({
            "round": int(row["RoundNumber"]), "circuit_key": key,
            "event_name": str(row["EventName"]) or (event_name(key) if key else "?"),
            "circuit": str(row["Location"]), "country": str(row["Country"]),
        })
    return races


def _context_json(ctx: RaceContext) -> dict[str, Any]:
    data = ctx.model_dump(mode="json")
    data["has_actual_result"] = bool(ctx.actual_result)
    return data


def _demo_result(ctx: RaceContext, scenario: str | None, session_id: str) -> SimulationResult:
    sim = demo_simulation(ctx, scenario)
    return SimulationResult(
        id=uuid.uuid4().hex[:12], session_id=session_id, kind="run", prompt=scenario,
        model="demo (offline pace model)", simulation=sim, points=validate.points_for(sim, ctx.year),
        issues=validate.check(sim, ctx), comparison=validate.compare_to_actual(sim, ctx.actual_result),
        usage=Usage(),
    )


def _make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: Any, content_type: str = "application/json",
                  filename: str | None = None) -> None:
            data = body if isinstance(body, bytes) else (
                body.encode() if isinstance(body, str) else json.dumps(body).encode())
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            parts = [p for p in url.path.split("/") if p]
            if not parts or parts[0] != "api":
                return self._static(url.path) if method == "GET" else self._send(404, {"error": "not found"})
            p = parts[1:]
            try:
                if method == "GET":
                    if p == ["status"]:
                        return self._send(200, app.status())
                    if p == ["seasons"]:
                        return self._send(200, app.seasons())
                    if len(p) == 2 and p[0] == "calendar":
                        return self._send(200, app.calendar(int(p[1])))
                    if len(p) == 3 and p[0] == "context":
                        source = parse_qs(url.query).get("source", ["auto"])[0]
                        ctx = app.cache.get(int(p[1]), int(p[2]), source)
                        if ctx is None:
                            return self._send(404, {"error": "race data not loaded yet"})
                        return self._send(200, {**_context_json(ctx), "prompt": ctx.to_prompt()})
                    if len(p) == 2 and p[0] == "jobs":
                        return self._send(200, app.job(p[1]))
                    if p == ["history"]:
                        return self._send(200, app.history.list_results())
                    if len(p) == 2 and p[0] == "results":
                        return self._send(200, app.result(p[1]))
                    if len(p) == 3 and p[0] == "results" and p[2] in ("export.md", "export.json"):
                        res = app.result(p[1])
                        stem = f"{res.get('year')}-{(res.get('event_name') or 'race').replace(' ', '-')}-{p[1]}"
                        if p[2] == "export.json":
                            payload = {k: res[k] for k in ("result", "context", "batch", "prompt", "created_at")}
                            return self._send(200, json.dumps(payload, indent=2), "application/json", f"{stem}.json")
                        md = to_markdown(res["result"], f"{res.get('year')} {res.get('event_name')}")
                        return self._send(200, md, "text/markdown; charset=utf-8", f"{stem}.md")
                if method == "POST":
                    handlers = {"prepare": app.prepare, "simulate": app.simulate, "whatif": app.what_if}
                    if len(p) == 1 and p[0] in handlers:
                        return self._send(202, handlers[p[0]](self._body()))
                if method == "DELETE" and len(p) == 2 and p[0] == "results":
                    if not app.history.delete_result(p[1]):
                        raise LookupError("unknown result")
                    return self._send(200, {"deleted": p[1]})
                return self._send(404, {"error": "not found"})
            except LookupError as exc:
                return self._send(404, {"error": str(exc).strip("'\"")})
            except (ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})
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

        def do_DELETE(self):
            self._route("DELETE")

        def log_message(self, fmt, *args):
            if "/api/jobs/" not in self.path:  # polling is noisy
                logger.info("%s %s", self.command, self.path)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI race simulator - local app")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--demo", action="store_true", help="never call Claude; use the offline demo model")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    app = App(demo=args.demo)
    server = ThreadingHTTPServer((args.host, args.port), _make_handler(app))
    mode = f"AI ({DEFAULT_MODEL})" if app.ai_available else "DEMO - set ANTHROPIC_API_KEY for AI simulations"
    print(f"\n  Race simulator on http://{args.host}:{args.port}  [{mode}]\n  Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
