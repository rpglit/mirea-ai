"""FA solver tests: methodic anchors (MATERIALS_ANALYSIS sections 3.3 and 8)."""

from __future__ import annotations

import pytest

from petrinet.errors import ValidationError
from petrinet.solvers.automata import (
    compare,
    normalize,
    simulate,
    to_enumeration,
    to_graph,
    to_mealy,
    to_table,
)
from petrinet.solvers.report import Report
from petrinet.solvers.solvers_fa import (
    BLACK_BOX,
    MEALY,
    MOORE,
    MOORE_110,
    MOORE_Z_GRAPH,
    MOORE_Z_TABLE,
    NO_OUTPUT,
    REGISTRY,
    WORD,
    solve_fa,
)

# --- normalize: three ways give one automaton --------------------------------

def test_normalize_three_ways_equal() -> None:
    by_triples = normalize(NO_OUTPUT)
    table: dict = {
        "P": NO_OUTPUT["P"],
        "S": NO_OUTPUT["S"],
        "s0": "s0",
        "type": "none",
        "phi": {"table": [["s0", "s0", "s1"], ["s1", "s1", "s2"], ["s2", "s2", "s0"]]},
    }
    by_table = normalize(table)
    graph: dict = {
        "P": NO_OUTPUT["P"],
        "S": NO_OUTPUT["S"],
        "s0": "s0",
        "type": "none",
        "phi": {
            "graph": {
                "nodes": [["s0"], ["s1"], ["s2"]],
                "edges": [
                    ["s0", "p1", "s0"],
                    ["s0", "p2", "s1"],
                    ["s1", "p1", "s1"],
                    ["s1", "p2", "s2"],
                    ["s2", "p1", "s2"],
                    ["s2", "p2", "s0"],
                ],
            }
        },
    }
    by_graph = normalize(graph)
    assert by_triples.phi == by_table.phi == by_graph.phi
    assert by_triples.s0 == "s0"


def test_normalize_incomplete_phi_rejected() -> None:
    spec = dict(NO_OUTPUT)
    spec["phi"] = [
        ["s0", "p1", "s0"],
        ["s0", "p2", "s1"],
        # missing the pairs of s1, s2
    ]
    with pytest.raises(ValidationError):
        normalize(spec)


def test_normalize_unknown_state_rejected() -> None:
    spec = dict(NO_OUTPUT)
    spec["phi"] = [["s0", "p1", "sX"], *NO_OUTPUT["phi"][1:]]
    with pytest.raises(ValidationError):
        normalize(spec)


# --- simulate: methodic anchors ----------------------------------------------

def test_fa01_black_box() -> None:
    r = simulate(normalize(BLACK_BOX), ["p3", "p1", "p3", "p2"])
    assert r["output_word"] == ["w2", "w1", "w2", "w2"]


def test_fa02_no_output_word() -> None:
    r = simulate(normalize(NO_OUTPUT), WORD)
    assert r["states"] == ["s0", "s0", "s1", "s2", "s2", "s0"]
    assert r["output_word"] == []
    assert r["ticks"][0][3] is None


def test_fa03_moore() -> None:
    r = simulate(normalize(MOORE), WORD)
    assert r["states"] == ["s0", "s0", "s1", "s3", "s3", "s0"]
    assert r["output_word"] == ["w0", "w1", "w0", "w0", "w0"]
    assert r["ticks"][0][3] == "w0*"  # w0* is marked and excluded from the word


def test_fa04_mealy() -> None:
    r = simulate(normalize(MEALY), WORD)
    assert r["states"] == ["s0", "s0", "s1", "s2", "s2", "s0"]
    assert r["output_word"] == ["w0", "w1", "w0", "w0", "w0"]
    assert r["ticks"][0][3] is None  # t0: no output in Mealy


def test_fa05_compare_moore_mealy() -> None:
    cmp = compare(normalize(MOORE), normalize(MEALY), WORD)
    assert cmp["equal"] is True
    assert cmp["r1"]["output_word"] == ["w0", "w1", "w0", "w0", "w0"]
    assert cmp["r2"]["output_word"] == ["w0", "w1", "w0", "w0", "w0"]


def test_simulate_unknown_symbol_rejected() -> None:
    with pytest.raises(ValidationError):
        simulate(normalize(NO_OUTPUT), ["p9"])


# --- representations ----------------------------------------------------------

def test_enumeration_moore() -> None:
    lines = to_enumeration(normalize(MOORE))
    assert "s0 = φ(s0, p1)" in lines
    assert "s0 = φ(s3, p2)" in lines
    assert "w1 = ψ(s1)" in lines
    assert len(lines) == 8 + 4


def test_table_moore_has_output_column() -> None:
    table = to_table(normalize(MOORE))
    assert table["rows"][0][0] == "s0/w0"
    assert table["cols"] == ["p1", "p2"]


def test_graph_mealy_arcs_labelled() -> None:
    graph = to_graph(normalize(MEALY))
    assert ["s0", "p2", "s1", "w1"] in graph["edges"]
    assert graph["s0"] == "s0"


def test_fa06_to_mealy_matches_figure_111() -> None:
    mealy = to_mealy(normalize(MOORE_110))
    graph = to_graph(mealy)
    arcs = {(e[0], e[1], e[2], e[3]) for e in graph["edges"]}
    expected = {
        ("s0", "p2", "s1", "w2"),
        ("s1", "p1", "s1", "w2"),
        ("s1", "p2", "s2", "w1"),
        ("s2", "p1", "s1", "w2"),
        ("s2", "p2", "s2", "w1"),
        # p1 from the initial vertex (completing the partial methodic graph):
        ("s0", "p1", "s0", "*"),
    }
    assert arcs == expected
    # analytic rule: Mealy output = Moore output of the TARGET state
    moore = normalize(MOORE_110)
    for si in moore.S:
        for pj in moore.P:
            assert mealy.psi[(si, pj)] == moore.psi[moore.phi[(si, pj)]]  # type: ignore[index]


def test_to_mealy_requires_moore() -> None:
    with pytest.raises(ValidationError):
        to_mealy(normalize(MEALY))


# --- solvers_fa: registry and reports -----------------------------------------

def test_registry_covers_all_eight() -> None:
    ids = {t.task_id for t in REGISTRY}
    assert ids == {f"TASK-FA-0{i}" for i in range(1, 9)}
    assert all(t.group == "FA" and t.input_kind == "fa" for t in REGISTRY)


def test_solve_fa03_report() -> None:
    report = solve_fa("TASK-FA-03", {"kind": "simulate", "input": MOORE, "word": WORD})
    assert isinstance(report, Report)
    assert report.answer["states"] == ["s0", "s0", "s1", "s3", "s3", "s0"]
    assert report.answer["output_word"] == ["w0", "w1", "w0", "w0", "w0"]
    data = report.to_dict()
    assert list(data) == sorted(data)  # deterministic key order
    assert data["task_id"] == "TASK-FA-03"


def test_solve_fa07_table_to_enumeration_and_graph() -> None:
    report = solve_fa("TASK-FA-07", {"kind": "normalize", "input": MOORE_Z_TABLE})
    enum = report.answer["enumeration"]
    assert "z1 = φ(z0, x1)" in enum
    assert "y2 = ψ(z0)" in enum
    assert len(enum) == 6 + 3
    graph = report.answer["graph"]
    assert graph["nodes"] == [["z0", "y2"], ["z1", "y1"], ["z2", "y1"]]
    assert len(graph["edges"]) == 6


def test_solve_fa08_graph_to_enumeration_and_table() -> None:
    report = solve_fa("TASK-FA-08", {"kind": "normalize", "input": MOORE_Z_GRAPH})
    enum = report.answer["enumeration"]
    assert "Z2 = φ(Z0, x1)" in enum
    assert "y2 = ψ(Z1)" in enum
    table = report.answer["table"]
    assert table["rows"][0][0] == "Z0/y1"
    assert table["rows"][0][1:] == ["Z2", "Z1"]


def test_solve_fa05_compare_report() -> None:
    report = solve_fa(
        "TASK-FA-05",
        {"kind": "compare", "input": MOORE, "input2": MEALY, "word": WORD},
    )
    assert report.answer["equal"] is True


def test_solve_fa06_to_mealy_report() -> None:
    report = solve_fa("TASK-FA-06", {"kind": "to_mealy", "input": MOORE_110})
    mealy = report.answer["mealy"]
    assert mealy["graph"]["edges"] and "enumeration" in mealy and "table" in mealy


def test_solve_unknown_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        solve_fa("TASK-FA-01", {"kind": "nope", "input": NO_OUTPUT})
