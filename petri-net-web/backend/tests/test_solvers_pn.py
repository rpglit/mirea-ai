"""PN solver tests: methodic anchors (MATERIALS_ANALYSIS sections 3.1 and 8)."""

from __future__ import annotations

import pytest

from petrinet.errors import UnknownTaskError, ValidationError
from petrinet.solvers.report import Report
from petrinet.solvers.solvers_pn import REGISTRY, solve_pn

SMOKE_NET = {
    "places": ["p1", "p2"],
    "transitions": ["t1"],
    "inputs": {"t1": {"p1": 1}},
    "outputs": {"t1": {"p2": 1}},
    "initial_marking": {"p1": 1, "p2": 0},
}


def _answer(task_id: str, **spec) -> dict:
    report = solve_pn(task_id, spec)
    assert isinstance(report, Report)
    return report.answer


# --- firing ------------------------------------------------------------------

def test_pn05_reference_chain() -> None:
    a = _answer("TASK-PN-05")
    assert [e["t"] for e in a["enabled"]] == ["t1", "t2", "t3", "t4", "t5"]
    assert a["final_marking"] == [5, 3, 4, 6, 3, 3]
    assert a["chain"]["executable"] is True
    assert a["chain"]["steps"][0]["from"] == [7, 4, 2, 5, 4, 3]


def test_pn03_double_arcs_cycle() -> None:
    a = _answer("TASK-PN-03")
    assert [e["t"] for e in a["enabled"]] == ["t1"]
    assert [s["to"] for s in a["chain"]["steps"]] == [[0, 2], [2, 0]]


def test_pn06_count() -> None:
    a = _answer("TASK-PN-06")
    assert a["count"] == 3
    assert a["final_marking"] == [0, 3, 3]
    assert [s["to"] for s in a["chain"]["steps"]] == [[2, 1, 1], [1, 2, 2], [0, 3, 3]]


def test_pn22_24_25_single_fire() -> None:
    assert _answer("TASK-PN-22")["final_marking"] == [0, 1]
    assert _answer("TASK-PN-24")["final_marking"] == [0, 0, 1]
    assert _answer("TASK-PN-25")["final_marking"] == [0, 1, 1]


def test_pn26_scenarios() -> None:
    a = _answer("TASK-PN-26")
    sc = a["scenarios"]
    assert sc[0]["final"] == [1, 1, 1]  # multiplicity 2: 3 >= 2
    assert sc[1]["enabled"] == []  # multiplicity 3: 2 < 3
    assert sc[1]["final"] == [2, 0, 0]  # marking unchanged
    assert sc[2]["final"] == [0, 1, 1]


# --- extend (PN-02) -----------------------------------------------------------

def test_pn02_extend() -> None:
    a = _answer("TASK-PN-02")
    assert [e["t"] for e in a["enabled"]] == ["t1", "t2"]
    assert a["pair_chains"]["t1_then_t2"]["failed_at"] == 2
    assert a["pair_chains"]["t2_then_t1"]["failed_at"] == 2
    assert a["mu_star"] == [1, 2, 1, 0, 0]
    assert a["mu_star_chain"]["executable"] is True
    assert a["mu_star_chain"]["final"] == [0, 0, 0, 1, 1]
    ext = a["extension"]
    assert ext["verification"]["executable"] is True
    assert ext["firing_counts"] == {"t1": 3, "t2": 3, "t3": 3, "t4": 3}
    assert ext["net"]["transitions"] == ["t1", "t2", "t3", "t4"]


# --- minimal marking -----------------------------------------------------------

def test_pn07_mu_min_and_parallel() -> None:
    a = _answer("TASK-PN-07")
    assert a["mu_min"] == [2, 2, 0]
    assert a["parallel"]["mu_parallel"] == [3, 3, 0]
    assert a["parallel"]["after_firing"] == [0, 0, 2]


def test_pn09_mu_min() -> None:
    a = _answer("TASK-PN-09")
    assert a["mu_min"] == [2, 2, 1, 2, 2]


def test_pn19_sequence_mu_min() -> None:
    a = _answer("TASK-PN-19")
    assert a["mu_min"] == [3, 0, 4]
    assert a["mu0"] == [3, 0, 4]
    assert a["final_marking"] == [0, 5, 0]
    assert a["chain"]["executable"] is True
    cls = a["classification"]
    assert cls["verdict"] == "тупиковая"
    assert cls["conservative"] is False


# --- classification ------------------------------------------------------------

def test_pn04_live_safe() -> None:
    cls = _answer("TASK-PN-04")["classification"]
    assert cls["verdict"] == "живая"
    assert cls["liveness_level"] == "L4"
    assert cls["k"] == 1
    assert cls["safe"] is True
    assert cls["deadlock_count"] == 0
    assert cls["conservative"] is False  # t2: 1 input, 2 outputs — sum is not constant


def test_pn21_partially_deadlocking() -> None:
    cls = _answer("TASK-PN-21")["classification"]
    # p3 is not replenished: t2 fires at most once — not live (methodic classes)
    assert cls["verdict"] == "частичнотупиковая"
    assert cls["per_transition"]["t2"]["level"] == "L1"
    assert cls["per_transition"]["t1"]["level"] == "L4"
    assert cls["k"] == 2
    assert cls["safe"] is False
    assert cls["conservative"] is False


def test_pn27_unbounded_live() -> None:
    cls = _answer("TASK-PN-27")["classification"]
    assert cls["structure"] == "coverability"
    assert cls["bounded"] is False
    assert cls["per_transition"]["t1"]["level"] == "L4"


def test_pn28_safe_conservative() -> None:
    cls = _answer("TASK-PN-28")["classification"]
    assert cls["verdict"] == "живая"
    assert cls["k"] == 1
    assert cls["safe"] is True
    assert cls["conservative"] is True


def test_pn29_k2_conservative() -> None:
    cls = _answer("TASK-PN-29")["classification"]
    assert cls["verdict"] == "живая"
    assert cls["k"] == 2
    assert cls["safe"] is False
    assert cls["conservative"] is True


def test_pn31_traffic_light() -> None:
    cls = _answer("TASK-PN-31")["classification"]
    assert cls["verdict"] == "живая"
    assert cls["safe"] is True
    assert cls["conservative"] is True


# --- matrices -------------------------------------------------------------------

def test_pn17_matrices_and_sequences() -> None:
    a = _answer("TASK-PN-17")
    assert a["matrices"]["W_minus"] == [[1, 0], [0, 1], [1, 1]]
    assert a["matrices"]["W_plus"] == [[0, 0], [0, 0], [1, 1]]
    assert [e["t"] for e in a["enabled"]] == ["t1", "t2"]
    s1, s2 = a["sequences"]
    assert s1["executable"] is False
    assert s1["failed_at"] == 4
    assert s2["executable"] is True
    assert s2["mu_prime"] == [0, 0, 1]


def test_pn18_matrices_match_methodic() -> None:
    a = _answer("TASK-PN-18")
    assert a["matrices"]["W_minus"] == [[1, 1, 0], [1, 1, 0], [1, 1, 0], [0, 0, 3]]
    assert a["matrices"]["W_plus"] == [[1, 0, 0], [0, 1, 1], [0, 1, 1], [1, 0, 0]]
    assert [e["t"] for e in a["enabled"]] == ["t1", "t2", "t3"]
    s = a["sequences"][0]
    assert s["executable"] is True
    assert s["v"] == [2, 2, 1]
    assert s["mu_prime"] == [0, 4, 2, 3]


def test_pn35_matrices_match_methodic() -> None:
    a = _answer("TASK-PN-35")
    assert a["matrices"]["W_minus"] == [[1, 0], [0, 1], [0, 1], [0, 0]]
    assert a["matrices"]["W_plus"] == [[0, 1], [1, 0], [1, 0], [0, 1]]
    assert a["matrices"]["W"] == [[-1, 1], [1, -1], [1, -1], [0, 1]]
    assert [e["t"] for e in a["enabled"]] == ["t1"]
    s = a["sequences"][0]
    assert s["v"] == [2, 1]
    assert s["mu_prime"] == [0, 1, 3, 2]


# --- Minsky machine ---------------------------------------------------------------

def test_pn38_inc() -> None:
    sc = _answer("TASK-PN-38")["scenarios"][0]
    assert sc["before"] == [1, 2, 0]
    assert sc["after"] == [0, 3, 1]


def test_pn39_dec_scenarios() -> None:
    sc = _answer("TASK-PN-39")["scenarios"]
    assert sc[0]["after"] == [0, 0, 0, 0, 1, 0, 1, 0]  # a: 1 -> 0, goto k
    assert sc[1]["after"] == [0, 0, 0, 0, 0, 0, 0, 1]  # a = 0, goto l


def test_pn40_halt() -> None:
    sc = _answer("TASK-PN-40")["scenarios"][0]
    assert sc["after"] == [0]


# --- model tasks --------------------------------------------------------------------

def test_model_tasks_provide_graph() -> None:
    for task_id in (
        "TASK-PN-01",
        "TASK-PN-11",
        "TASK-PN-12",
        "TASK-PN-13",
        "TASK-PN-14",
        "TASK-PN-16",
        "TASK-PN-20",
        "TASK-PN-34",
    ):
        a = _answer(task_id)
        assert a["graph"]["places"], task_id
        assert a["graph"]["arcs"], task_id
        assert a["analytic"]["P"], task_id


def test_pn12_bathroom_mutex() -> None:
    a = _answer("TASK-PN-12")
    assert a["invariants"]
    places = {p[0] for p in a["graph"]["places"]}
    assert "bath" in places


# --- registry and custom tasks -------------------------------------------------------

def test_registry_covers_pn_catalog() -> None:
    ids = {t.task_id for t in REGISTRY}
    assert len(ids) == 33
    assert "TASK-PN-05" in ids
    # extended-model tasks (priorities/temporal/inhibitor/colored) live in pn_ext
    for missing in ("TASK-PN-10", "TASK-PN-15", "TASK-PN-30", "TASK-PN-32",
                    "TASK-PN-33", "TASK-PN-36", "TASK-PN-37"):
        assert missing not in ids
    assert all(t.group == "PN" and t.input_kind == "pn" for t in REGISTRY)


def test_unknown_task_raises() -> None:
    with pytest.raises(UnknownTaskError):
        solve_pn("TASK-PN-99", {})


def test_custom_group_validation() -> None:
    with pytest.raises(ValidationError):
        solve_pn("custom:nope", {})
    with pytest.raises(ValidationError):
        solve_pn("custom:firing", {})  # no net


def test_custom_firing() -> None:
    report = solve_pn(
        "custom:firing",
        {"net": SMOKE_NET, "sequence": ["t1", "t1"]},
    )
    assert report.answer["final_marking"] == [0, 1]
    assert report.answer["chain"]["executable"] is False
    assert report.answer["chain"]["failed_at"] == 2
    data = report.to_dict()
    assert list(data) == sorted(data)


def test_max_steps_validation() -> None:
    with pytest.raises(ValidationError):
        solve_pn("TASK-PN-05", {"max_steps": 0})
    with pytest.raises(ValidationError):
        solve_pn("TASK-PN-05", {"max_steps": 100000})


def test_report_structure() -> None:
    data = solve_pn("TASK-PN-05").to_dict()
    assert data["task_id"] == "TASK-PN-05"
    assert data["given"]["statement"]
    assert data["find"]
    assert [s["step"] for s in data["solution"]] == list(range(1, len(data["solution"]) + 1))
    assert solve_pn("TASK-PN-08").to_dict()["notes"]
