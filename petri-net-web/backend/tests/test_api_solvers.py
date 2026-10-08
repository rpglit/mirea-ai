"""API tests, part 2: solver endpoints (ARCH section 2.6) and error localization."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from conftest import SMOKE_JSON, SMOKE_TEXT
from fastapi.testclient import TestClient

from petrinet.api import routes
from petrinet.api.app import create_app
from petrinet.config import Settings
from petrinet.storage import SessionStore


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Test client with an isolated temp SQLite store."""
    settings = Settings(
        log_level="WARNING",
        db_path=str(tmp_path / "sessions.db"),
        reach_max_markings=50000,
        petrinet_static_dir=str(tmp_path / "static"),
    )
    app = create_app(settings)
    previous_store = routes._store
    routes._store = SessionStore(settings.db_path)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        routes._store = previous_store


def _parse(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/parse", json={"format": "text", "payload": SMOKE_TEXT, **overrides})
    assert response.status_code == 201
    return cast("dict[str, object]", response.json())


# --- POST /solve -----------------------------------------------------------------


def test_solve_pn_catalog(client: TestClient) -> None:
    response = client.post("/solve", json={"task_id": "TASK-PN-05"})
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    assert body["task_id"] == "TASK-PN-05"
    assert body["given"]
    assert body["find"]
    assert body["solution"]
    answer = cast("dict[str, object]", body["answer"])
    assert answer["final_marking"] == [5, 3, 4, 6, 3, 3]
    keys = list(body)
    assert keys == sorted(keys)


def test_solve_lss_catalog(client: TestClient) -> None:
    response = client.post("/solve", json={"task_id": "TASK-LSS-08"})
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    answer = cast("dict[str, object]", body["answer"])
    assert answer["phi"] == "1/(s + 5)"


def test_solve_fa_catalog(client: TestClient) -> None:
    response = client.post("/solve", json={"task_id": "TASK-FA-03"})
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    answer = cast("dict[str, object]", body["answer"])
    assert answer["states"] == ["s0", "s0", "s1", "s3", "s3", "s0"]
    assert answer["output_word"] == ["w0", "w1", "w0", "w0", "w0"]


def test_solve_custom_firing(client: TestClient) -> None:
    net = dict(SMOKE_JSON)
    response = client.post(
        "/solve",
        json={"task_id": "custom:firing", "data": {"net": net, "sequence": ["t1", "t2"]}},
    )
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    answer = cast("dict[str, object]", body["answer"])
    assert answer["final_marking"] == [4, 5, 4, 5, 4, 2]


def test_solve_unknown_task(client: TestClient) -> None:
    response = client.post("/solve", json={"task_id": "TASK-XX-01"})
    assert response.status_code == 422
    body = cast("dict[str, object]", response.json())
    error = cast("dict[str, object]", body["error"])
    assert error["code"] == "unknown_task"
    assert "TASK-XX-01" in str(error["message"])


def test_solve_validation_error(client: TestClient) -> None:
    response = client.post("/solve", json={"task_id": "custom:firing", "data": {}})
    assert response.status_code == 422
    body = cast("dict[str, object]", response.json())
    assert cast("dict[str, object]", body["error"])["code"] == "validation_failed"


def test_solve_russian_errors(client: TestClient) -> None:
    response = client.post("/solve", json={"task_id": "custom:firing", "data": {}})
    error = cast("dict[str, object]", cast("dict[str, object]", response.json())["error"])
    assert str(error["message"]).startswith("ошибка валидации")


def test_solve_solver_failed(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from petrinet import solvers
    from petrinet.errors import SolverError

    def _boom(task_id: str, data: dict[str, object] | None = None) -> object:
        raise SolverError("линейная система несовместна")

    monkeypatch.setattr(solvers, "solve", _boom)
    response = client.post("/solve", json={"task_id": "TASK-LSS-04"})
    assert response.status_code == 500
    body = cast("dict[str, object]", response.json())
    error = cast("dict[str, object]", body["error"])
    assert error["code"] == "solver_failed"
    assert str(error["message"]).startswith("ошибка решателя")


# --- GET /catalog -------------------------------------------------------------------


def test_catalog_full_and_filtered(client: TestClient) -> None:
    response = client.get("/catalog")
    assert response.status_code == 200
    rows = cast("list[dict[str, object]]", response.json())
    assert len(rows) == 71
    groups = {}
    for row in rows:
        groups[str(row["group"])] = groups.get(str(row["group"]), 0) + 1
    assert groups == {"PN": 40, "LSS": 23, "FA": 8}
    assert set(rows[0]) == {"task_id", "group", "title", "source", "type", "input_kind"}

    assert len(cast("list[object]", client.get("/catalog?group=PN").json())) == 40
    assert len(cast("list[object]", client.get("/catalog?group=LSS").json())) == 23
    assert len(cast("list[object]", client.get("/catalog?group=FA").json())) == 8
    assert client.get("/catalog?group=XX").status_code == 422


# --- POST /matrices and /minimal-marking ------------------------------------------------


def test_matrices_smoke(client: TestClient) -> None:
    session_id = str(_parse(client)["session_id"])
    response = client.post("/matrices", json={"session_id": session_id})
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    assert body["W_minus"][0] == [2, 1, 0, 0, 0]
    assert body["W_plus"][4] == [0, 0, 0, 1, 0]
    assert body["W"][0] == [-2, -1, 0, 0, 1]


def test_matrices_unknown_session(client: TestClient) -> None:
    response = client.post("/matrices", json={"session_id": "nope"})
    assert response.status_code == 404
    body = cast("dict[str, object]", response.json())
    error = cast("dict[str, object]", body["error"])
    assert error["code"] == "unknown_session"
    assert str(error["message"]).startswith("неизвестная сессия")


def test_minimal_marking_smoke(client: TestClient) -> None:
    session_id = str(_parse(client)["session_id"])
    response = client.post("/minimal-marking", json={"session_id": session_id})
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    assert body["mu_min"] == [2, 1, 1, 2, 2, 1]
    per_t = cast("dict[str, object]", body["per_transition"])
    assert per_t["t4"] == [0, 1, 1, 2, 0, 0]

    parallel = client.post("/minimal-marking", json={"session_id": session_id, "parallel": True})
    pbody = cast("dict[str, object]", parallel.json())
    assert pbody["mu_min"] == [3, 2, 1, 2, 2, 1]


def test_matrices_colored_rejected(client: TestClient) -> None:
    payload = dict(SMOKE_JSON)
    payload["colors"] = {
        "initial_values": {"p1": ["a"]},
        "guards": {},
        "output_exprs": {},
    }
    response = client.post("/parse", json={"format": "json", "payload": payload})
    assert response.status_code == 201
    session_id = str(cast("dict[str, object]", response.json())["session_id"])
    matrices = client.post("/matrices", json={"session_id": session_id})
    assert matrices.status_code == 422
    error = cast("dict[str, object]", cast("dict[str, object]", matrices.json())["error"])
    assert error["code"] == "unsupported_model"
    minimal = client.post("/minimal-marking", json={"session_id": session_id})
    assert minimal.status_code == 422


# --- POST /properties (extended) ---------------------------------------------------------


def test_properties_extended(client: TestClient) -> None:
    session_id = str(_parse(client)["session_id"])
    client.post("/graph", json={"session_id": session_id})
    response = client.post(
        "/properties",
        json={
            "session_id": session_id,
            "with": {"matrices": True, "mu_min": True, "sequence": ["t1", "t2", "t3", "t4", "t5"]},
        },
    )
    assert response.status_code == 200
    body = cast("dict[str, object]", response.json())
    assert body["verdict"] == "тупиковая"
    assert body["conservative"]
    assert body["mu_min"] == [2, 1, 1, 2, 2, 1]
    matrices = cast("dict[str, object]", body["matrices"])
    assert matrices["W_minus"][0] == [2, 1, 0, 0, 0]
    sequence = cast("dict[str, object]", body["sequence"])
    assert sequence["executable"] is True
    assert sequence["v"] == [1, 1, 1, 1, 1]
    assert sequence["mu_prime"] == [5, 3, 4, 6, 3, 3]


def test_properties_sequence_bad_transition(client: TestClient) -> None:
    session_id = str(_parse(client)["session_id"])
    client.post("/graph", json={"session_id": session_id})
    response = client.post(
        "/properties",
        json={"session_id": session_id, "with": {"sequence": ["t99"]}},
    )
    assert response.status_code == 422


# --- GET /sessions limit and POST /parse v2 fields ----------------------------------------


def test_sessions_limit(client: TestClient) -> None:
    for i in range(3):
        _parse(client, name=f"s{i}")
    assert len(cast("list[object]", client.get("/sessions").json())) == 3
    assert len(cast("list[object]", client.get("/sessions?limit=2").json())) == 2
    assert client.get("/sessions?limit=0").status_code == 422
    rows = cast("list[dict[str, object]]", client.get("/sessions").json())
    assert rows[0]["name"] == "s2"  # newest first


def test_parse_returns_v2_fields(client: TestClient) -> None:
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
    response = client.post("/parse", json={"format": "json", "payload": payload, "name": "v2"})
    assert response.status_code == 201
    body = cast("dict[str, object]", response.json())
    assert body["inhibitors"] == {"t1": [], "t2": ["p2"]}
    assert body["priorities"] == {"t1": 1, "t2": 0}
    assert body["delays"] == {"t1": [["p2", 3]]}
    assert "colors" not in body
