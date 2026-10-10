"""Tests for the solver package entry points (catalog/solve, ARCH section 2.5)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, cast

import pytest

from petrinet import solvers
from petrinet.errors import UnknownTaskError
from petrinet.solvers import CATALOG, catalog, solve


def test_catalog_size_and_groups() -> None:
    assert len(CATALOG) == 71
    by_group = {}
    for task in CATALOG:
        by_group[task.group] = by_group.get(task.group, 0) + 1
    assert by_group == {"PN": 40, "LSS": 23, "FA": 8}


def test_catalog_filter() -> None:
    assert len(catalog("PN")) == 40
    assert len(catalog("LSS")) == 23
    assert len(catalog("FA")) == 8
    with pytest.raises(UnknownTaskError):
        catalog("XX")


def test_solve_smoke_from_each_domain() -> None:
    report = solve("TASK-PN-05")
    assert report.answer["final_marking"] == [5, 3, 4, 6, 3, 3]
    report = solve("TASK-LSS-08")
    assert report.answer["phi"] == "1/(s + 5)"
    report = solve("TASK-FA-03")
    assert report.answer["states"] == ["s0", "s0", "s1", "s3", "s3", "s0"]
    assert report.answer["output_word"] == ["w0", "w1", "w0", "w0", "w0"]


def test_solve_unknown() -> None:
    with pytest.raises(UnknownTaskError):
        solve("TASK-XX-01")


def test_custom_via_package() -> None:
    net = {
        "places": ["p1"],
        "transitions": ["t1"],
        "inputs": {"t1": {"p1": 1}},
        "outputs": {"t1": {"p1": 1}},
        "initial_marking": {"p1": 1},
    }
    report = solve("custom:firing", {"net": net, "sequence": ["t1"]})
    assert report.answer["final_marking"] == [1]


def test_all_catalog_reports_json_serializable() -> None:
    """Regression: to_dict() must be plain JSON for every catalog task —
    sympy leftovers (Rational/Zero/Matrix) are canonicalized in Report.to_dict."""
    for info in CATALOG:
        report = solve(info.task_id)
        dumped = json.dumps(report.to_dict(), sort_keys=True)
        assert dumped


def test_solve_future_inflight_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Property (ARCH §2.6, D-060): parallel identical solve_future calls share
    one in-flight worker — the underlying solve runs exactly once.

    The second call is made while the first solve is provably in flight
    (``gate``), so the only way to observe one solve run is in-flight
    deduplication: both calls return the same future.
    """
    real_solve = solvers.solve
    state = {"calls": 0}
    lock = threading.Lock()
    gate = threading.Event()

    def counted(task_id: str, data: dict[str, Any] | None = None) -> Any:
        with lock:
            state["calls"] += 1
            first = state["calls"] == 1
        if first:
            gate.set()
            time.sleep(0.3)
        return real_solve(task_id, data)

    monkeypatch.setattr(solvers, "solve", counted)
    solvers._solve_cache.clear()

    future1 = solvers.solve_future("TASK-PN-05")
    assert gate.wait(10.0), "первый solve не стартовал"
    future2 = solvers.solve_future("TASK-PN-05")
    assert future2 is future1, "in-flight дедупликация: ожидаем один future"
    report = future1.result(timeout=30)
    assert cast(list[int], report.answer["final_marking"]) == [5, 3, 4, 6, 3, 3]
    assert state["calls"] == 1, f"solve вызван {state['calls']} раза, ожидается 1"
