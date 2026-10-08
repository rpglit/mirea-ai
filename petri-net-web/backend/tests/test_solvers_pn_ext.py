"""PN ext solver tests: priorities, temporal, inhibitors, colored (methodic anchors)."""

from __future__ import annotations

import pytest

from petrinet.errors import UnknownTaskError, ValidationError
from petrinet.solvers.report import Report
from petrinet.solvers.solvers_pn_ext import REGISTRY, solve_pn_ext


def _answer(task_id: str, **spec) -> dict:
    report = solve_pn_ext(task_id, spec)
    assert isinstance(report, Report)
    return report.answer


# --- priorities (M8) ------------------------------------------------------------

def test_pn30_priority_conflict() -> None:
    a = _answer("TASK-PN-30")
    sc = a["scenarios"]
    first = sc[0]["trace"][0]
    assert first["enabled"] == ["t1", "t2"]
    assert first["active"] == ["t1"]
    assert first["excluded"][0]["t"] == "t2"
    assert "Pr 1 > Pr 0" in first["excluded"][0]["reason"]
    assert sc[0]["final"] == [2, 0, 1, 0]
    second = sc[1]["trace"][0]
    assert second["active"] == ["t2"]
    assert second["excluded"] == []
    assert sc[1]["final"] == [0, 0, 0, 1]


def test_pn10_server_model() -> None:
    a = _answer("TASK-PN-10")
    assert a["invariants"]
    sc = a["scenarios"][0]
    assert sc["final"] == [0, 0, 2, 0, 0, 2]  # 2 free slots back, 2 results
    assert len(sc["trace"]) == 6
    graph = a["graph"]
    assert [p for p, _ in graph["places"] if p == "f"] == ["f"]


def test_pn10_capacity_never_exceeded() -> None:
    a = _answer("TASK-PN-10")
    sc = a["scenarios"][0]
    for entry in sc["trace"]:
        w, w2 = entry["marking"][3], entry["marking"][4]
        assert w + w2 <= 2


# --- temporal nets (M9) -----------------------------------------------------------

def test_pn15_period_9_ticks() -> None:
    a = _answer("TASK-PN-15")
    assert a["period"] == 9
    ticks = a["ticks"]
    # phase a (green 1) holds 3 ticks: t1 fires at 0, b arrives at 3
    assert ticks[0]["fired"] == ["t1"]
    assert ticks[0]["in_flight"] == [["b", 3, 1]]
    assert ticks[3]["fired"] == ["t2"]
    assert ticks[8]["fired"] == ["t5"]
    # the same state repeats after 9 ticks
    assert ticks[0]["fired"] == ticks[9]["fired"]
    assert ticks[0]["in_flight"] == ticks[9]["in_flight"]


def test_pn32_period_8_ticks() -> None:
    a = _answer("TASK-PN-32")
    assert a["period"] == 8
    ticks = a["ticks"]
    assert ticks[0]["fired"] == ["t2"]
    assert ticks[0]["in_flight"] == [["r", 4, 1]]
    assert ticks[4]["fired"] == ["t3"]
    assert ticks[7]["fired"] == ["t1"]


def test_temporal_custom_net() -> None:
    net = {
        "places": ["p1", "p2"],
        "transitions": ["t1"],
        "inputs": {"t1": {"p1": 1}},
        "outputs": {"t1": {"p2": 1}},
        "initial_marking": {"p1": 1, "p2": 0},
        "delays": {"t1": {"p2": 2}},
    }
    a = _answer("custom:temporal", net=net, horizon=5)
    assert a["ticks"][0]["in_flight"] == [["p2", 2, 1]]
    assert a["ticks"][1]["marking"] == [0, 0]
    assert a["ticks"][2]["marking"] == [0, 1]


# --- inhibitors (M2 with ⊣) ---------------------------------------------------------

def test_pn33_dec_scenarios() -> None:
    a = _answer("TASK-PN-33")
    sc = a["scenarios"]
    assert sc[0]["after"] == [2, 0, 1, 0]  # a: 3 -> 2, k = 1
    assert sc[1]["after"] == [0, 0, 0, 1]  # a = 0, goto l
    assert sc[0]["trace"][0]["enabled"] is True
    assert sc[1]["trace"][0]["inhibitor_blocked"] == []


def test_inhibitor_blocks_transition() -> None:
    net = {
        "places": ["a", "i", "k", "l"],
        "transitions": ["t1", "t2"],
        "inputs": {"t1": {"a": 1, "i": 1}, "t2": {"i": 1}},
        "outputs": {"t1": {"k": 1}, "t2": {"l": 1}},
        "initial_marking": {"a": 1, "i": 1, "k": 0, "l": 0},
        "inhibitors": {"t2": ["a"]},
    }
    a = _answer("custom:inhibitor", net=net, scenarios=[{"name": "s", "sequence": ["t2"]}])
    entry = a["scenarios"][0]["trace"][0]
    assert entry["inputs_ok"] is True
    assert entry["inhibitor_blocked"] == ["a"]
    assert entry["enabled"] is False


# --- colored nets (M12, A-21) --------------------------------------------------------

def test_pn36_guard_expressions() -> None:
    a = _answer("TASK-PN-36")
    evaluated = {e["expr"]: e for e in a["evaluated"]}
    assert evaluated["a-1"] == {"expr": "a-1", "kind": "output", "value": 1}
    assert evaluated["a>1"]["kind"] == "guard"
    assert evaluated["a>1"]["value"] is True
    assert evaluated["b=1"]["value"] is True
    assert evaluated["b>1"]["value"] is False
    assert evaluated["b×c"] == {"expr": "b×c", "kind": "output", "value": 3}


def test_pn37_coffee_machine() -> None:
    a = _answer("TASK-PN-37")
    trace = a["trace"]
    assert trace[0]["marking"] == [0, 1, 0, 1, 1, 1, 0]
    assert trace[1]["marking"] == [0, 0, 0, 0, 0, 0, 1]  # coffee ready
    assert "горячая" in trace[0]["colors"]


def test_guard_unknown_variable_rejected() -> None:
    with pytest.raises(ValidationError):
        _answer(
            "custom:colored",
            net=None,
            expressions=["q > 1"],
            values={"a": 1},
        )


def test_guard_bad_syntax_rejected() -> None:
    with pytest.raises(ValidationError):
        _answer(
            "custom:colored",
            net=None,
            expressions=["a +"],
            values={"a": 1},
        )


# --- registry ------------------------------------------------------------------------

def test_registry_covers_ext_tasks() -> None:
    ids = {t.task_id for t in REGISTRY}
    assert ids == {
        "TASK-PN-10",
        "TASK-PN-15",
        "TASK-PN-30",
        "TASK-PN-32",
        "TASK-PN-33",
        "TASK-PN-36",
        "TASK-PN-37",
    }
    assert all(t.group == "PN" and t.input_kind == "pn" for t in REGISTRY)


def test_unknown_task_raises() -> None:
    with pytest.raises(UnknownTaskError):
        solve_pn_ext("TASK-PN-99", {})


def test_custom_group_validation() -> None:
    with pytest.raises(ValidationError):
        solve_pn_ext("custom:nope", {})
    with pytest.raises(ValidationError):
        solve_pn_ext("custom:model", {"net": {}})


def test_report_structure() -> None:
    data = solve_pn_ext("TASK-PN-36").to_dict()
    assert data["task_id"] == "TASK-PN-36"
    assert data["given"]["statement"]
    assert data["find"]
    assert [s["step"] for s in data["solution"]] == list(range(1, len(data["solution"]) + 1))
    assert data["notes"]
