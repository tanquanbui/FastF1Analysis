"""Server job flow in demo mode: simulate -> poll -> history -> export -> delete."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from simulator import server, store


@pytest.fixture
def base_url(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    app = server.App(demo=True)
    app.cache = store.ContextCache(tmp_path)
    app.history = store.History(tmp_path / "sim.db")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def call(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if resp.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def wait(base, job_id):
    for _ in range(100):
        _, job = call(f"{base}/api/jobs/{job_id}")
        if job["state"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job never finished")


def test_simulate_history_export_delete(base_url):
    status, job = call(f"{base_url}/api/simulate", "POST", {"year": 2024, "round": 5, "source": "fixtures"})
    assert status == 202
    job = wait(base_url, job["id"])
    assert job["state"] == "done", job
    rid = job["output"]["result_id"]

    _, cal = call(f"{base_url}/api/calendar/2024")
    assert cal[4]["cached_sources"] == ["fixtures"]

    _, res = call(f"{base_url}/api/results/{rid}")
    assert res["mode"] == "demo" and res["context"]["circuit"]["key"] == "shanghai"
    assert res["can_what_if"] is False
    assert res["result"]["comparison"]["actual_order"][0] == "VER"

    _, hist = call(f"{base_url}/api/history")
    assert [h["id"] for h in hist] == [rid]

    status, md = call(f"{base_url}/api/results/{rid}/export.md")
    assert status == 200 and md.startswith("# [DEMO]")

    status, err = call(f"{base_url}/api/whatif", "POST", {"session_id": res["session_id"], "question": "x"})
    assert status == 400

    assert call(f"{base_url}/api/results/{rid}", "DELETE")[0] == 200
    assert call(f"{base_url}/api/results/{rid}")[0] == 404


def test_context_requires_prepare(base_url):
    assert call(f"{base_url}/api/context/2024/5?source=fixtures")[0] == 404
    _, job = call(f"{base_url}/api/prepare", "POST", {"year": 2024, "round": 5, "source": "fixtures"})
    assert wait(base_url, job["id"])["state"] == "done"
    status, ctx = call(f"{base_url}/api/context/2024/5?source=fixtures")
    assert status == 200 and "prompt" in ctx and "actual_result" not in ctx
