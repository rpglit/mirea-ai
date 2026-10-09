"""API tests, part 3: iteration-3 audit fixes (ARCH section 2.6).

P1#2 — ``POST /solve`` outside the event loop (sync ``def`` + daemon worker
+ ``future.result(timeout)`` + in-flight deduplication); P1#3 —
``GET /sessions/{id}`` carries the v2 model fields; P2#7 — static
``Cache-Control`` headers.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from conftest import SMOKE_TEXT
from fastapi.testclient import TestClient

from petrinet import solvers
from petrinet.api import routes
from petrinet.api.app import create_app
from petrinet.config import Settings
from petrinet.storage import SessionStore

ASSET_NAME = "index-abc123.js"


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Test client with an isolated store and a minimal static frontend."""
    static_dir = tmp_path / "static"
    assets = static_dir / "assets"
    assets.mkdir(parents=True)
    (static_dir / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    (assets / ASSET_NAME).write_text("console.log(1);", encoding="utf-8")
    settings = Settings(
        log_level="WARNING",
        db_path=str(tmp_path / "sessions.db"),
        reach_max_markings=50000,
        petrinet_static_dir=str(static_dir),
    )
    app = create_app(settings)
    previous_store = routes._store
    routes._store = SessionStore(settings.db_path)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        routes._store = previous_store


def _error_of(response: TestClient) -> dict[str, object]:
    """Return the ``error`` block of a typed error body."""
    body: dict[str, object] = response.json()
    return cast("dict[str, object]", body["error"])


# --- P1#2: /solve outside the event loop -----------------------------------------


def test_solve_lss10_returns_report(client: TestClient) -> None:
    """POST /solve TASK-LSS-10 answers 200 with the full methodic report."""
    response = client.post("/solve", json={"task_id": "TASK-LSS-10"})
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    assert body["task_id"] == "TASK-LSS-10"
    for key in ("answer", "find", "given", "notes", "solution"):
        assert key in body
    assert list(body) == sorted(body)
    assert cast("dict[str, object]", body["answer"])


def test_solve_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """While a 0.5 s solve runs in the worker, /healthz answers in < 50 ms."""
    real_solve = solvers.solve
    started = threading.Event()

    def slow_solve(task_id: str, data: dict[str, object] | None = None) -> object:
        started.set()
        time.sleep(0.5)
        return real_solve(task_id, data)

    monkeypatch.setattr(solvers, "solve", slow_solve)

    outcome: dict[str, int] = {}

    def _run() -> None:
        response = client.post("/solve", json={"task_id": "TASK-LSS-10"})
        outcome["status"] = response.status_code

    solve_thread = threading.Thread(target=_run)
    solve_thread.start()
    assert started.wait(5.0)
    began = time.perf_counter()
    health = client.get("/healthz")
    health_ms = (time.perf_counter() - began) * 1000
    solve_thread.join(10)
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health_ms < 50
    assert outcome.get("status") == 200


def test_solve_timeout_returns_500_then_cache_hit(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """timeout 0.1 s vs a 0.5 s solve -> 500 solver_failed; the worker keeps
    running and caches its report, so a retry after it finishes -> 200."""
    real_solve = solvers.solve
    done = threading.Event()
    state = {"slow": True}

    def slow_once(task_id: str, data: dict[str, object] | None = None) -> object:
        if state["slow"]:
            state["slow"] = False
            time.sleep(0.5)
            report = real_solve(task_id, data)
            done.set()
            return report
        return real_solve(task_id, data)

    monkeypatch.setattr(solvers, "solve", slow_once)
    monkeypatch.setattr(solvers, "SOLVER_TIMEOUT_S", 0.1)
    solvers._solve_cache.clear()

    failed = client.post("/solve", json={"task_id": "TASK-LSS-10"})
    assert failed.status_code == 500
    error = _error_of(failed)
    assert error["code"] == "solver_failed"
    assert "таймаут" in str(error["message"])
    assert "0.1" in str(error["message"])

    assert done.wait(5.0)
    retried = client.post("/solve", json={"task_id": "TASK-LSS-10"})
    assert retried.status_code == 200
    body = cast("dict[str, object]", retried.json())
    assert body["task_id"] == "TASK-LSS-10"
    assert body["answer"]


def test_solve_inflight_dedup(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Two identical parallel /solve calls share one worker: one solve run."""
    real_solve = solvers.solve
    state = {"calls": 0}
    lock = threading.Lock()

    def counted(task_id: str, data: dict[str, object] | None = None) -> object:
        with lock:
            state["calls"] += 1
            first = state["calls"] == 1
        if first:
            time.sleep(0.3)
        return real_solve(task_id, data)

    monkeypatch.setattr(solvers, "solve", counted)
    solvers._solve_cache.clear()

    outcomes: dict[str, int] = {}

    def _run(name: str) -> None:
        response = client.post("/solve", json={"task_id": "TASK-PN-05"})
        outcomes[name] = response.status_code

    threads = [threading.Thread(target=_run, args=(name,)) for name in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert outcomes == {"a": 200, "b": 200}
    assert state["calls"] == 1


# --- P1#3: GET /sessions/{id} carries the v2 model fields -------------------------


def test_get_session_inhibitor_from_form(client: TestClient) -> None:
    """A session parsed from a form with an inhibitor arc keeps it on reopen."""
    arcs = [
        {"source": "p1", "target": "t1", "weight": 1, "direction": "input"},
        {"source": "t1", "target": "p2", "weight": 1, "direction": "output"},
        {"source": "p1", "target": "t2", "weight": 1, "direction": "input"},
        {"source": "t2", "target": "p2", "weight": 1, "direction": "output"},
        {"source": "p2", "target": "t2", "weight": 1, "direction": "inhibitor"},
    ]
    payload = {
        "places": ["p1", "p2"],
        "transitions": ["t1", "t2"],
        "arcs": arcs,
        "initial_marking": {"p1": 1, "p2": 0},
    }
    created = client.post("/parse", json={"format": "form", "payload": payload, "name": "inh"})
    assert created.status_code == 201
    parse_body = cast("dict[str, object]", created.json())
    session_id = str(parse_body["session_id"])
    assert parse_body["inhibitors"] == {"t1": [], "t2": ["p2"]}

    summary = cast("dict[str, object]", client.get(f"/sessions/{session_id}").json())
    assert summary["inhibitors"] == parse_body["inhibitors"] == {"t1": [], "t2": ["p2"]}


def test_get_session_all_v2_fields(client: TestClient) -> None:
    """inhibitors/priorities/delays round-trip from the stored model_json."""
    payload = {
        "places": ["p1", "p2"],
        "transitions": ["t1", "t2"],
        "inputs": {"t1": {"p1": 1}, "t2": {"p1": 1}},
        "outputs": {"t1": {"p2": 1}, "t2": {"p2": 1}},
        "initial_marking": {"p1": 1, "p2": 0},
        "inhibitors": {"t2": ["p2"]},
        "priorities": {"t1": 1, "t2": 0},
        "delays": {"t1": {"p2": 3}},
    }
    created = client.post("/parse", json={"format": "json", "payload": payload, "name": "v2"})
    assert created.status_code == 201
    session_id = str(cast("dict[str, object]", created.json())["session_id"])

    body = cast("dict[str, object]", client.get(f"/sessions/{session_id}").json())
    assert body["inhibitors"] == {"t1": [], "t2": ["p2"]}
    assert body["priorities"] == {"t1": 1, "t2": 0}
    assert body["delays"] == {"t1": {"p2": 3}}
    assert "colors" not in body


def test_get_session_without_v2_fields_omits_keys(client: TestClient) -> None:
    """A classic net: the v2 keys are absent (not empty objects), like /parse."""
    created = client.post("/parse", json={"format": "text", "payload": SMOKE_TEXT})
    assert created.status_code == 201
    parse_body = cast("dict[str, object]", created.json())
    assert "inhibitors" not in parse_body
    session_id = str(parse_body["session_id"])

    body = cast("dict[str, object]", client.get(f"/sessions/{session_id}").json())
    for key in ("inhibitors", "priorities", "delays", "colors"):
        assert key not in body


# --- P2#7: static Cache-Control ----------------------------------------------------


def test_static_assets_immutable(client: TestClient) -> None:
    """Vite content-hashed assets are cached forever; misses get no header."""
    response = client.get(f"/assets/{ASSET_NAME}")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"

    missing = client.get("/assets/missing.js")
    assert missing.status_code == 404
    assert "Cache-Control" not in missing.headers


def test_static_index_no_cache(client: TestClient) -> None:
    """The SPA entry is revalidated on every load (new builds picked up)."""
    for path in ("/", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-cache"


def test_api_routes_have_no_cache_control(client: TestClient) -> None:
    """API responses (health and parse) are untouched by the static policy."""
    health = client.get("/healthz")
    assert health.status_code == 200
    assert "Cache-Control" not in health.headers

    parsed = client.post("/parse", json={"format": "text", "payload": SMOKE_TEXT})
    assert parsed.status_code == 201
    assert "Cache-Control" not in parsed.headers
