"""API tests, part 1: happy-path smoke-net flows (contract: ARCHITECTURE.md 'API routes')."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from conftest import SMOKE_JSON, SMOKE_TEXT
from fastapi.testclient import TestClient

from petrinet.api import routes
from petrinet.api.app import create_app
from petrinet.config import Settings
from petrinet.storage import SessionStore

SMOKE_PLACES = ["p1", "p2", "p3", "p4", "p5", "p6"]
SMOKE_TRANSITIONS = ["t1", "t2", "t3", "t4", "t5"]
SMOKE_INITIAL = [7, 4, 2, 5, 4, 3]

COUNTER_TEXT = "P = {p1}, T = {t1},\nI(t1) = {}, O(t1) = {p1},\nµ = (1).\n"


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Test client with an isolated temp SQLite store and quiet logging."""
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
    """POST /parse with the smoke text payload; return the 201 body."""
    response = client.post("/parse", json={"format": "text", "payload": SMOKE_TEXT, **overrides})
    assert response.status_code == 201
    body: dict[str, object] = response.json()
    return body


def test_parse_text_smoke(client: TestClient) -> None:
    """POST /parse (text) returns the smoke model and a 32-char session id."""
    body = _parse(client)
    assert body["places"] == SMOKE_PLACES
    assert body["transitions"] == SMOKE_TRANSITIONS
    assert body["initial_marking"] == SMOKE_INITIAL
    assert "session_id" in body
    session_id = body["session_id"]
    assert isinstance(session_id, str)
    assert len(session_id) == 32


def test_parse_json_and_form_equivalent(client: TestClient) -> None:
    """The json and form channels produce the same model as the text channel."""
    text_body = _parse(client)
    json_response = client.post("/parse", json={"format": "json", "payload": SMOKE_JSON})
    assert json_response.status_code == 201
    json_body: dict[str, object] = json_response.json()

    inputs = cast("dict[str, dict[str, int]]", SMOKE_JSON["inputs"])
    outputs = cast("dict[str, dict[str, int]]", SMOKE_JSON["outputs"])
    arcs: list[dict[str, object]] = []
    for t in SMOKE_TRANSITIONS:
        for p, w in inputs[t].items():
            arcs.append({"source": p, "target": t, "weight": w, "direction": "input"})
        for p, w in outputs[t].items():
            arcs.append({"source": t, "target": p, "weight": w, "direction": "output"})
    assert len(arcs) == 15
    form_payload = json.loads(
        json.dumps(
            {
                "arcs": arcs,
                "initial_marking": SMOKE_JSON["initial_marking"],
                "places": SMOKE_PLACES,
                "transitions": SMOKE_TRANSITIONS,
            }
        )
    )
    form_response = client.post("/parse", json={"format": "form", "payload": form_payload})
    assert form_response.status_code == 201
    form_body: dict[str, object] = form_response.json()

    for body in (text_body, json_body, form_body):
        assert body["places"] == text_body["places"]
        assert body["transitions"] == text_body["transitions"]
        assert body["initial_marking"] == text_body["initial_marking"]


def test_full_smoke_flow(client: TestClient) -> None:
    """Parse -> graph -> properties -> fire/undo/reset -> goto -> state (D-009..D-014)."""
    sid = str(_parse(client)["session_id"])

    graph_response = client.post("/graph", json={"session_id": sid})
    assert graph_response.status_code == 200
    graph_body: dict[str, object] = graph_response.json()
    assert graph_body["kind"] == "graph"
    assert graph_body["node_count"] == 1503
    assert graph_body["edge_count"] == 4983
    assert graph_body["capped"] is False
    structure = cast("dict[str, object]", graph_body["structure"])
    nodes = cast("list[object]", structure["nodes"])
    edges = cast("list[object]", structure["edges"])
    assert nodes[0] == ["n0", SMOKE_INITIAL]
    assert edges[0] == ["n0", "t1", "n1"]
    assert len(nodes) == 1503

    properties_response = client.post("/properties", json={"session_id": sid})
    assert properties_response.status_code == 200
    report: dict[str, object] = properties_response.json()
    assert report["global_k"] == 29
    assert report["bounded"] is True
    assert report["safe"] is False
    liveness = {
        "level": "L1",
        "transitions": {t: {"level": "L1", "occurs": True} for t in SMOKE_TRANSITIONS},
    }
    assert report["liveness"] == liveness
    assert len(cast("list[object]", report["deadlocks"])) == 23
    assert report["dead_transitions"] == []
    assert report["home_state"] is False
    assert report["deadlock_free"] is False
    assert report["approximation"] is None
    assert report["stats"] == {"edge_count": 4983, "node_count": 1503}

    fire_response = client.post(
        "/fire", json={"session_id": sid, "action": "fire", "transition": "t1"}
    )
    assert fire_response.status_code == 200
    fire_body: dict[str, object] = fire_response.json()
    assert fire_body["current_marking"] == [5, 5, 2, 5, 4, 3]
    assert len(cast("list[str]", fire_body["active_transitions"])) > 0
    tail = cast("list[dict[str, object]]", fire_body["history_tail"])
    assert tail[-1] == {
        "kind": "fire",
        "transition": "t1",
        "from": SMOKE_INITIAL,
        "to": [5, 5, 2, 5, 4, 3],
    }

    undo_body: dict[str, object] = client.post(
        "/fire", json={"session_id": sid, "action": "undo"}
    ).json()
    assert undo_body["current_marking"] == SMOKE_INITIAL

    reset_body: dict[str, object] = client.post(
        "/fire", json={"session_id": sid, "action": "reset"}
    ).json()
    assert reset_body["current_marking"] == SMOKE_INITIAL
    assert reset_body["history_tail"] == []

    goto_body: dict[str, object] = client.post(
        "/goto", json={"session_id": sid, "marking": [6, 4, 4, 5, 4, 2]}
    ).json()
    assert goto_body["current_marking"] == [6, 4, 4, 5, 4, 2]

    state_response = client.get(f"/state/{sid}")
    assert state_response.status_code == 200
    state_body: dict[str, object] = state_response.json()
    assert state_body["current_marking"] == [6, 4, 4, 5, 4, 2]
    history = cast("list[dict[str, object]]", state_body["history"])
    assert len(history) == 1
    assert history[0] == {
        "kind": "goto",
        "transition": None,
        "from": SMOKE_INITIAL,
        "to": [6, 4, 4, 5, 4, 2],
    }
    active = cast("list[str]", state_body["active_transitions"])
    assert all(t in SMOKE_TRANSITIONS for t in active)


def test_properties_with_queries(client: TestClient) -> None:
    """/properties answers reachable/coverable marking queries (FR-010 fixture)."""
    sid = str(_parse(client)["session_id"])
    assert client.post("/graph", json={"session_id": sid}).status_code == 200
    response = client.post(
        "/properties",
        json={
            "session_id": sid,
            "queries": {
                "reachable_marking": [5, 5, 2, 5, 4, 3],
                "coverable_marking": [11, 0, 0, 0, 0, 0],
            },
        },
    )
    assert response.status_code == 200
    body: dict[str, object] = response.json()
    assert body["queries"] == {
        "is_coverable": {"11,0,0,0,0,0": False},
        "is_reachable": {"5,5,2,5,4,3": True},
    }


def test_session_list_and_summary(client: TestClient) -> None:
    """/sessions lists one summary row; /sessions/{id} flags built artifacts."""
    sid = str(_parse(client)["session_id"])

    list_response = client.get("/sessions")
    assert list_response.status_code == 200
    items = cast("list[dict[str, object]]", list_response.json())
    assert len(items) == 1
    item = items[0]
    for key in ("session_id", "name", "created_at", "places", "transitions"):
        assert key in item
    assert item["session_id"] == sid
    assert item["places"] == SMOKE_PLACES
    assert item["transitions"] == SMOKE_TRANSITIONS

    summary: dict[str, object] = client.get(f"/sessions/{sid}").json()
    assert summary["graph_built"] is False
    assert summary["report_computed"] is False

    assert client.post("/graph", json={"session_id": sid}).status_code == 200
    assert client.post("/properties", json={"session_id": sid}).status_code == 200
    summary_after: dict[str, object] = client.get(f"/sessions/{sid}").json()
    assert summary_after["graph_built"] is True
    assert summary_after["report_computed"] is True


def test_delete_session(client: TestClient) -> None:
    """DELETE removes the session; later /state is a 404 unknown_session."""
    sid = str(_parse(client)["session_id"])
    assert client.delete(f"/sessions/{sid}").status_code == 204
    assert client.get("/sessions").json() == []
    state_response = client.get(f"/state/{sid}")
    assert state_response.status_code == 404
    error_body: dict[str, object] = state_response.json()
    assert cast("dict[str, object]", error_body["error"])["code"] == "unknown_session"


def _error_of(response: httpx.Response) -> dict[str, object]:
    """Return the ``error`` block of a typed error body (the only top-level key)."""
    body: dict[str, object] = response.json()
    assert set(body) == {"error"}
    return cast("dict[str, object]", body["error"])


def _problems(response: httpx.Response) -> list[dict[str, object]]:
    """Return the ``details`` array from a 422 ``validation_failed`` body."""
    error = _error_of(response)
    assert error["code"] == "validation_failed"
    return cast("list[dict[str, object]]", error["details"])


def test_error_bodies_shape(client: TestClient) -> None:
    """Typed error bodies are exactly {"error": {code, message, details}} (ADR-0006)."""
    not_found = client.get("/state/doesnotexist")
    assert not_found.status_code == 404
    missing = _error_of(not_found)
    assert set(missing) == {"code", "message", "details"}
    assert missing["code"] == "unknown_session"
    assert isinstance(missing["message"], str)
    assert missing["details"] == {"session_id": "doesnotexist"}

    garbage = client.post("/parse", json={"format": "text", "payload": "garbage"})
    assert garbage.status_code == 422
    failed = _error_of(garbage)
    assert set(failed) == {"code", "message", "details"}
    assert failed["code"] == "parse_failed"
    assert isinstance(failed["message"], str)
    assert isinstance(failed["details"], dict)


def test_parse_error_paths(client: TestClient) -> None:
    """Bad intake payloads yield 422 validation_failed with concrete problems."""
    wrong_type = client.post("/parse", json={"format": "text", "payload": {"places": []}})
    assert wrong_type.status_code == 422
    _problems(wrong_type)

    no_marking = json.loads(json.dumps(SMOKE_JSON))
    del no_marking["initial_marking"]
    missing = client.post("/parse", json={"format": "json", "payload": no_marking})
    assert missing.status_code == 422
    problems = _problems(missing)
    assert len(problems) > 0
    for problem in problems:
        assert set(problem) == {"path", "message"}

    unknown_place = json.loads(json.dumps(SMOKE_JSON))
    unknown_place["inputs"] = {"t1": {"px": 1}}
    bad_input = client.post("/parse", json={"format": "json", "payload": unknown_place})
    assert bad_input.status_code == 422
    assert any(str(p["path"]).startswith("inputs.") for p in _problems(bad_input))

    dup_arc = {"source": "p1", "target": "t1", "weight": 2, "direction": "input"}
    duplicate = {
        "arcs": [dup_arc, json.loads(json.dumps(dup_arc))],
        "initial_marking": SMOKE_JSON["initial_marking"],
        "places": SMOKE_PLACES,
        "transitions": SMOKE_TRANSITIONS,
    }
    dup_response = client.post("/parse", json={"format": "form", "payload": duplicate})
    assert dup_response.status_code == 422
    assert any("duplicate arc" in str(p["message"]) for p in _problems(dup_response))

    sideways = {
        "arcs": [{"source": "p1", "target": "t1", "weight": 2, "direction": "sideways"}],
        "initial_marking": SMOKE_JSON["initial_marking"],
        "places": SMOKE_PLACES,
        "transitions": SMOKE_TRANSITIONS,
    }
    side_response = client.post("/parse", json={"format": "form", "payload": sideways})
    assert side_response.status_code == 422
    assert any(str(p["path"]).endswith(".direction") for p in _problems(side_response))


def test_fire_error_paths(client: TestClient) -> None:
    """Fire failures: missing transition (422), disabled at deadlock (409), undo (422)."""
    sid = str(_parse(client)["session_id"])
    assert client.post("/graph", json={"session_id": sid}).status_code == 200

    missing_t = client.post("/fire", json={"session_id": sid, "action": "fire"})
    assert missing_t.status_code == 422
    _problems(missing_t)

    report: dict[str, object] = client.post("/properties", json={"session_id": sid}).json()
    deadlocks = cast("list[list[int]]", report["deadlocks"])
    assert len(deadlocks) > 0
    target = deadlocks[0]
    assert client.post("/goto", json={"session_id": sid, "marking": target}).status_code == 200
    blocked = client.post("/fire", json={"session_id": sid, "action": "fire", "transition": "t1"})
    assert blocked.status_code == 409
    blocked_error = _error_of(blocked)
    assert blocked_error["code"] == "transition_not_enabled"
    details = cast("dict[str, object]", blocked_error["details"])
    assert details["transition"] == "t1"
    assert details["marking"] == target

    fresh_sid = str(_parse(client)["session_id"])
    undo = client.post("/fire", json={"session_id": fresh_sid, "action": "undo"})
    assert undo.status_code == 422
    assert any("undo" in str(p["message"]) for p in _problems(undo))


def test_goto_error_paths(client: TestClient) -> None:
    """Goto fails with 422 when the target is not a graph node (or has a wrong length)."""
    sid = str(_parse(client)["session_id"])
    assert client.post("/graph", json={"session_id": sid}).status_code == 200

    not_a_node = client.post("/goto", json={"session_id": sid, "marking": [99, 0, 0, 0, 0, 0]})
    assert not_a_node.status_code == 422
    problems = _problems(not_a_node)
    assert str(problems[0]["path"]) == "marking"

    wrong_length = client.post("/goto", json={"session_id": sid, "marking": [1, 2]})
    assert wrong_length.status_code == 422
    _problems(wrong_length)


def test_properties_before_graph(client: TestClient) -> None:
    """/properties before /graph is a 422 naming the missing graph."""
    sid = str(_parse(client)["session_id"])
    response = client.post("/properties", json={"session_id": sid})
    assert response.status_code == 422
    assert any("graph" in str(p["message"]) for p in _problems(response))


def test_export_report(client: TestClient) -> None:
    """Report export is a JSON attachment; 422 while no report is stored yet."""
    sid = str(_parse(client)["session_id"])
    assert client.post("/graph", json={"session_id": sid}).status_code == 200
    assert client.post("/properties", json={"session_id": sid}).status_code == 200

    response = client.get(f"/sessions/{sid}/export/report")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    disposition = response.headers.get("content-disposition", "")
    assert 'filename="report.json"' in disposition
    report: dict[str, object] = response.json()
    assert report["global_k"] == 29
    liveness = cast("dict[str, object]", report["liveness"])
    assert liveness["level"] == "L1"
    assert len(cast("list[object]", report["deadlocks"])) == 23

    fresh_sid = str(_parse(client)["session_id"])
    assert client.post("/graph", json={"session_id": fresh_sid}).status_code == 200
    no_report = client.get(f"/sessions/{fresh_sid}/export/report")
    assert no_report.status_code == 422
    _problems(no_report)


def test_export_markings_csv(client: TestClient) -> None:
    """Markings export is a CSV attachment; 422 while no graph is stored yet."""
    sid = str(_parse(client)["session_id"])
    assert client.post("/graph", json={"session_id": sid}).status_code == 200

    response = client.get(f"/sessions/{sid}/export/markings")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    disposition = response.headers.get("content-disposition", "")
    assert 'filename="markings.csv"' in disposition
    lines = response.text.splitlines()
    assert lines[0] == "p1,p2,p3,p4,p5,p6"
    assert lines[1] == "7,4,2,5,4,3"
    assert len(lines) == 1504
    assert "omega" not in response.text

    fresh_sid = str(_parse(client)["session_id"])
    no_graph = client.get(f"/sessions/{fresh_sid}/export/markings")
    assert no_graph.status_code == 422
    _problems(no_graph)


def test_cap_and_coverability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The cap aborts the exact build (413); coverability compresses the counter to omega."""
    settings = Settings(
        log_level="WARNING",
        db_path=str(tmp_path / "sessions.db"),
        reach_max_markings=1000,
        petrinet_static_dir=str(tmp_path / "static"),
    )
    app = create_app(settings)
    monkeypatch.setattr(routes, "_store", SessionStore(settings.db_path))
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    with TestClient(app) as client:
        body = _parse(client, payload=COUNTER_TEXT)
        assert body["places"] == ["p1"]
        assert body["initial_marking"] == [1]
        sid = str(body["session_id"])

        capped = client.post("/graph", json={"session_id": sid, "mode": "auto"})
        assert capped.status_code == 413
        capped_error = _error_of(capped)
        assert capped_error["code"] == "cap_exceeded"
        details = cast("dict[str, object]", capped_error["details"])
        assert details["limit"] == 1000
        assert details["suggestion"] == "coverability"

        tree_response = client.post("/graph", json={"session_id": sid, "mode": "coverability"})
        assert tree_response.status_code == 200
        tree_body: dict[str, object] = tree_response.json()
        assert tree_body["kind"] == "coverability"
        assert tree_body["node_count"] == 1
        tree_structure = cast("dict[str, object]", tree_body["structure"])
        assert tree_structure["nodes"] == [["n0", [None]]]

        report_response = client.post("/properties", json={"session_id": sid})
        assert report_response.status_code == 200
        report: dict[str, object] = report_response.json()
        assert report["approximation"] == "omega"
        assert report["per_place_k"] == {"p1": None}
        assert report["global_k"] is None
        assert report["bounded"] is False
        liveness = cast("dict[str, object]", report["liveness"])
        assert liveness["level"] == "L4"
        assert report["deadlock_free"] is True
