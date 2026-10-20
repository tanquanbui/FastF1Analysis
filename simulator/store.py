"""Local persistence: cached race contexts (JSON) and simulation history (SQLite).

Everything lives under ``data/`` (override with ``SIM_DATA_DIR``):

    data/contexts/2024-05-fastf1.json   race context, built once, reused forever
    data/simulator.db                   sessions (incl. conversation) + results
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .context import ROOT, RaceContext

DATA_DIR = Path(os.environ.get("SIM_DATA_DIR", ROOT / "data"))


class ContextCache:
    def __init__(self, root: Path | None = None):
        self.root = (root or DATA_DIR) / "contexts"

    def path(self, year: int, round_number: int, source: str) -> Path:
        return self.root / f"{year}-{round_number:02d}-{source}.json"

    def get(self, year: int, round_number: int, source: str) -> RaceContext | None:
        p = self.path(year, round_number, source)
        if not p.exists():
            return None
        return RaceContext.model_validate(json.loads(p.read_text()))

    def put(self, ctx: RaceContext, source: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.path(ctx.year, ctx.round or 0, source)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(ctx.to_cache()))
        tmp.replace(p)
        return p

    def delete(self, year: int, round_number: int, source: str) -> None:
        self.path(year, round_number, source).unlink(missing_ok=True)

    def cached_rounds(self, year: int) -> dict[int, list[str]]:
        """{round: [sources cached]} for the race picker."""
        out: dict[int, list[str]] = {}
        if not self.root.exists():
            return out
        for p in self.root.glob(f"{year}-*.json"):
            _, rnd, source = p.stem.split("-", 2)
            out.setdefault(int(rnd), []).append(source)
        return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    year INTEGER NOT NULL,
    round INTEGER,
    event_name TEXT NOT NULL,
    source TEXT,
    model TEXT,
    context_json TEXT NOT NULL,
    messages_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    batch_id TEXT,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    mode TEXT NOT NULL,
    prompt TEXT,
    headline TEXT,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    summary_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS results_session ON results(session_id);
CREATE INDEX IF NOT EXISTS results_created ON results(created_at);
"""


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "simulator.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._db.execute(sql, args)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    # ---- sessions
    def save_session(self, session: Any, source: str, model: str | None = None) -> None:
        ctx: RaceContext = session.context
        self._exec(
            """INSERT INTO sessions (id, created_at, year, round, event_name, source, model, context_json, messages_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET messages_json = excluded.messages_json""",
            (session.id, time.time(), ctx.year, ctx.round, ctx.event_name, source, model or session.simulator.model,
             json.dumps(ctx.to_cache()), json.dumps(session.messages)),
        )

    def load_session(self, session_id: str) -> tuple[RaceContext, list[dict[str, Any]], str] | None:
        rows = self._exec("SELECT context_json, messages_json, source FROM sessions WHERE id = ?", (session_id,))
        if not rows:
            return None
        r = rows[0]
        return RaceContext.model_validate(json.loads(r["context_json"])), json.loads(r["messages_json"]), r["source"]

    # ---- results
    def save_result(self, result: Any, mode: str, batch_id: str | None = None) -> None:
        self._exec(
            """INSERT OR REPLACE INTO results (id, session_id, batch_id, created_at, kind, mode, prompt, headline, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.id, result.session_id, batch_id, time.time(), result.kind, mode, result.prompt,
             result.simulation.headline, result.model_dump_json()),
        )

    def save_batch(self, batch_id: str, summary: dict[str, Any]) -> None:
        self._exec("INSERT OR REPLACE INTO batches (id, created_at, summary_json) VALUES (?, ?, ?)",
                   (batch_id, time.time(), json.dumps(summary)))

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        rows = self._exec("SELECT summary_json FROM batches WHERE id = ?", (batch_id,))
        return json.loads(rows[0]["summary_json"]) if rows else None

    def batch_result_ids(self, batch_id: str) -> list[str]:
        rows = self._exec("SELECT id FROM results WHERE batch_id = ? ORDER BY created_at", (batch_id,))
        return [r["id"] for r in rows]

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        rows = self._exec(
            """SELECT r.*, s.year, s.round, s.event_name, s.source FROM results r
               LEFT JOIN sessions s ON s.id = r.session_id WHERE r.id = ?""",
            (result_id,),
        )
        return self._row(rows[0], full=True) if rows else None

    def session_results(self, session_id: str) -> list[dict[str, Any]]:
        rows = self._exec(
            """SELECT r.*, s.year, s.round, s.event_name, s.source FROM results r
               LEFT JOIN sessions s ON s.id = r.session_id WHERE r.session_id = ? ORDER BY r.created_at""",
            (session_id,),
        )
        return [self._row(r, full=True) for r in rows]

    def list_results(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._exec(
            """SELECT r.id, r.session_id, r.batch_id, r.created_at, r.kind, r.mode, r.prompt, r.headline,
                      s.year, s.round, s.event_name, s.source
               FROM results r LEFT JOIN sessions s ON s.id = r.session_id
               ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        )
        return [self._row(r) for r in rows]

    def delete_result(self, result_id: str) -> bool:
        rows = self._exec("SELECT session_id FROM results WHERE id = ?", (result_id,))
        if not rows:
            return False
        self._exec("DELETE FROM results WHERE id = ?", (result_id,))
        sid = rows[0]["session_id"]
        if not self._exec("SELECT 1 FROM results WHERE session_id = ? LIMIT 1", (sid,)):
            self._exec("DELETE FROM sessions WHERE id = ?", (sid,))
        return True

    @staticmethod
    def _row(row: sqlite3.Row, full: bool = False) -> dict[str, Any]:
        d = {k: row[k] for k in row.keys() if k != "result_json"}
        if full:
            d["result"] = json.loads(row["result_json"])
        return d
