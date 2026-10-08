"""Tests for the solver package entry points (catalog/solve, ARCH section 2.5)."""

from __future__ import annotations

import json

import pytest

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
