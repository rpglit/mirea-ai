"""Tests for the phase 4.4 properties extension: M5 (conservative/verdict),
M6 (mu_min) and M7 (sequence_report) per the handbook (MATERIALS_ANALYSIS §3.1,
§5.1, §7.1, §8)."""

from __future__ import annotations

import pytest
from conftest import smoke_net
from hypothesis import assume, given, settings
from test_reachability import counter_net, small_net_strategy

from petrinet.core import Marking, PetriNet
from petrinet.errors import CapExceededError
from petrinet.properties import analyze, conservative, sequence_report, verdict
from petrinet.reachability import MarkingOrOmega, ReachableStructure, build


def example8_net() -> PetriNet:
    """Handbook Example 8 (TASK-PN-28): cycle p1→t1→p2→t2→p1, µ=(1,0)."""
    return PetriNet(
        places=("p1", "p2"),
        transitions=("t1", "t2"),
        inputs=((("p1", 1),), (("p2", 1),)),
        outputs=((("p2", 1),), (("p1", 1),)),
        initial_marking=(1, 0),
    )


def pn09_net() -> PetriNet:
    """TASK-PN-09: 5×4, reference µmin=(2,2,1,2,2); not conservative."""
    return PetriNet(
        places=("p1", "p2", "p3", "p4", "p5"),
        transitions=("t1", "t2", "t3", "t4"),
        inputs=(
            (("p1", 2), ("p3", 1)),
            (("p2", 2),),
            (("p4", 2), ("p5", 2)),
            (("p4", 2),),
        ),
        outputs=(
            (("p4", 2),),
            (("p4", 1), ("p5", 1)),
            (("p1", 1), ("p2", 1)),
            (("p2", 1), ("p3", 1)),
        ),
        initial_marking=(2, 2, 1, 2, 2),
    )


def pn07_net() -> PetriNet:
    """Handbook Example 2 (TASK-PN-23): I(t1)={p1,p1,p2}, I(t2)={p1,p2,p2}, O={p3}."""
    return PetriNet(
        places=("p1", "p2", "p3"),
        transitions=("t1", "t2"),
        inputs=((("p1", 2), ("p2", 1)), (("p1", 1), ("p2", 2))),
        outputs=((("p3", 1),), (("p3", 1),)),
        initial_marking=(2, 2, 0),
    )


def pn17_net() -> PetriNet:
    """TASK-PN-17: 3×2, µ=(2,1,1); σ=(t1,t1,t2,t2) is not executable."""
    return PetriNet(
        places=("p1", "p2", "p3"),
        transitions=("t1", "t2"),
        inputs=((("p1", 1), ("p3", 1)), (("p2", 1), ("p3", 1))),
        outputs=((("p3", 1),), (("p3", 1),)),
        initial_marking=(2, 1, 1),
    )


def pn35_net() -> PetriNet:
    """TASK-PN-35: 4×2, µ=(1,0,2,1), σ=(t1,t2,t1) → (0,1,3,2)."""
    return PetriNet(
        places=("p1", "p2", "p3", "p4"),
        transitions=("t1", "t2"),
        inputs=((("p1", 1),), (("p2", 1), ("p3", 1))),
        outputs=((("p2", 1), ("p3", 1)), (("p1", 1), ("p4", 1))),
        initial_marking=(1, 0, 2, 1),
    )


def two_component_net() -> PetriNet:
    """Two-component net (D-052): t1 is a p1 self-loop, t2 consumes p2, µ=(1,1).

    Has a cycle (t1) and a dying transition (t2), yet NO deadlocking marking —
    the counter-example to the old "deadlocks ≠ ∅" deadlocking criterion.
    """
    return PetriNet(
        places=("p1", "p2"),
        transitions=("t1", "t2"),
        inputs=((("p1", 1),), (("p2", 1),)),
        outputs=((("p1", 1),), ()),
        initial_marking=(1, 1),
    )


def test_conservative_example8() -> None:
    """Handbook Example 8: balanced transitions + constant sum 1 → conservative."""
    net = example8_net()
    structure = build(net, "auto")
    info = conservative(net, structure)
    assert info["conservative"] is True
    assert info["constant_sum"] is True
    assert info["per_transition"] == {
        "t1": {"in": 1, "out": 1, "equal": True},
        "t2": {"in": 1, "out": 1, "equal": True},
    }


def test_conservative_pn09() -> None:
    """TASK-PN-09: t1 in 3 / out 2 and t3 in 4 / out 2 → not conservative."""
    net = pn09_net()
    structure = build(net, "auto")
    info = conservative(net, structure)
    assert info["conservative"] is False
    assert info["per_transition"] == {
        "t1": {"in": 3, "out": 2, "equal": False},
        "t2": {"in": 2, "out": 2, "equal": True},
        "t3": {"in": 4, "out": 2, "equal": False},
        "t4": {"in": 2, "out": 2, "equal": True},
    }


def test_conservative_smoke() -> None:
    """Smoke net (6×5): t1 in 2 / out 1 → not conservative."""
    net = smoke_net()
    info = conservative(net, build(net, "auto"))
    assert info["conservative"] is False
    assert info["per_transition"]["t1"] == {"in": 2, "out": 1, "equal": False}


def test_verdict_smoke_deadlocking() -> None:
    """Smoke net (DAG, D-035; 23 deadlocks; L1) → «тупиковая»."""
    net = smoke_net()
    structure = build(net, "auto")
    report = analyze(net, structure)
    assert report.liveness.level == "L1"
    assert report.verdict == "тупиковая"
    assert verdict(structure, report) == "тупиковая"
    assert report.conservative == conservative(net, structure)
    assert report.mu_min is None


def test_verdict_example8_live() -> None:
    """Handbook Example 8: all transitions L4 → «живая»."""
    net = example8_net()
    structure = build(net, "auto")
    report = analyze(net, structure)
    assert report.liveness.level == "L4"
    assert report.verdict == "живая"
    assert verdict(structure, report) == "живая"
    assert report.conservative["conservative"] is True


def test_verdict_two_component_partial() -> None:
    """Two-component net: cycle + dying t2, zero deadlocks → «частичнотупиковая».

    Under the old "deadlocks ≠ ∅" criterion this net would NOT be deadlocking;
    it is the D-052 counter-example.
    """
    net = two_component_net()
    structure = build(net, "auto")
    report = analyze(net, structure)
    assert report.liveness.level == "L1"
    assert report.liveness.transitions["t1"].level == "L4"
    assert report.liveness.transitions["t2"].level == "L1"
    assert report.deadlocks == []
    assert report.verdict == "частичнотупиковая"
    assert verdict(structure, report) == "частичнотупиковая"


def test_verdict_coverability_none() -> None:
    """Coverability structure (omega node): the verdict is undetermined → None."""
    net = counter_net()
    structure = build(net, "coverability")
    report = analyze(net, structure)
    assert report.verdict is None
    assert verdict(structure, report) is None
    assert report.conservative["constant_sum"] is False


def test_sequence_report_pn05() -> None:
    """TASK-PN-05: σ=(t1..t5) from µ=(7,4,2,5,4,3) → (5,3,4,6,3,3), v=(1,1,1,1,1)."""
    net = smoke_net()
    report = sequence_report(net, (7, 4, 2, 5, 4, 3), ("t1", "t2", "t3", "t4", "t5"))
    assert report["executable"] is True
    assert report["failed_at"] is None
    assert report["v"] == [1, 1, 1, 1, 1]
    assert report["mu_prime"] == [5, 3, 4, 6, 3, 3]
    steps = report["steps"]
    assert len(steps) == 5
    assert steps[0] == {
        "transition": "t1",
        "from": [7, 4, 2, 5, 4, 3],
        "to": [5, 5, 2, 5, 4, 3],
        "enabled": True,
    }
    assert [step["transition"] for step in steps] == ["t1", "t2", "t3", "t4", "t5"]
    assert steps[-1]["to"] == [5, 3, 4, 6, 3, 3]


def test_sequence_report_pn17_not_executable() -> None:
    """TASK-PN-17: σ=(t1,t1,t2,t2) from (2,1,1) fails at step 4 (p2=0 at 2nd t2)."""
    net = pn17_net()
    report = sequence_report(net, (2, 1, 1), ("t1", "t1", "t2", "t2"))
    assert report["executable"] is False
    assert report["failed_at"] == 4
    assert report["mu_prime"] is None
    assert report["v"] == [2, 2]
    steps = report["steps"]
    assert len(steps) == 4
    assert steps[2] == {"transition": "t2", "from": [0, 1, 1], "to": [0, 0, 1], "enabled": True}
    assert steps[3] == {"transition": "t2", "from": [0, 0, 1], "to": None, "enabled": False}


def test_sequence_report_pn35() -> None:
    """TASK-PN-35: σ=(t1,t2,t1) from (1,0,2,1) → v=(2,1), µ′=(0,1,3,2)."""
    net = pn35_net()
    report = sequence_report(net, (1, 0, 2, 1), ("t1", "t2", "t1"))
    assert report["executable"] is True
    assert report["failed_at"] is None
    assert report["v"] == [2, 1]
    assert report["mu_prime"] == [0, 1, 3, 2]


def test_sequence_report_validation() -> None:
    """Unknown transition and wrong marking length raise ValueError."""
    net = smoke_net()
    with pytest.raises(ValueError, match="unknown transition"):
        sequence_report(net, (7, 4, 2, 5, 4, 3), ("t1", "t9"))
    with pytest.raises(ValueError, match="length"):
        sequence_report(net, (1, 2), ("t1",))


def test_mu_min_pn09() -> None:
    """TASK-PN-09 with_mu_min: µmin=(2,2,1,2,2); default analyze leaves it None."""
    net = pn09_net()
    structure = build(net, "auto")
    report = analyze(net, structure, with_mu_min=True)
    assert report.mu_min == [2, 2, 1, 2, 2]
    plain = analyze(net, structure)
    assert plain.mu_min is None


def test_mu_min_pn07_parallel() -> None:
    """Handbook Example 2: sequential µmin=(2,2,0); parallel variant (3,3,0)."""
    net = pn07_net()
    structure = build(net, "auto")
    sequential = analyze(net, structure, with_mu_min=True)
    assert sequential.mu_min == [2, 2, 0]
    parallel = analyze(net, structure, with_mu_min=True, parallel_mu_min=True)
    assert parallel.mu_min == [3, 3, 0]


def _build_or_skip(net: PetriNet) -> ReachableStructure:
    """Build the auto graph with a small cap; skip unbounded examples (fast)."""
    try:
        return build(net, "auto", cap=3000)
    except CapExceededError:
        assume(False)


def _as_marking(m: MarkingOrOmega) -> Marking:
    """Graph-kind node labels are concrete markings; assert it explicitly."""
    values: list[int] = []
    for v in m:
        assert v is not None
        values.append(v)
    return tuple(values)


def _is_dag(structure: ReachableStructure) -> bool:
    """Independent DAG check: iterative three-color DFS (no SCC / Tarjan)."""
    successors: dict[str, list[str]] = {nid: [] for nid, _m in structure.nodes}
    for src, _t, dst in structure.edges:
        successors[src].append(dst)
    white, gray, black = 0, 1, 2
    color: dict[str, int] = {nid: white for nid in successors}
    for start in successors:
        if color[start] != white:
            continue
        color[start] = gray
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, pos = stack[-1]
            children = successors[node]
            if pos < len(children):
                stack[-1] = (node, pos + 1)
                child = children[pos]
                if color[child] == gray:
                    return False
                if color[child] == white:
                    color[child] = gray
                    stack.append((child, 0))
            else:
                color[node] = black
                stack.pop()
    return True


def _strongly_live(net: PetriNet, structure: ReachableStructure) -> bool:
    """Independent L4 check: from every node, every transition is enabled at some
    node of its forward closure (forward per-node reachability, no backwards
    closure of the enablement set)."""
    markings = {nid: m for nid, m in structure.nodes}
    successors: dict[str, list[str]] = {nid: [] for nid in markings}
    for src, _t, dst in structure.edges:
        successors[src].append(dst)
    for start in markings:
        seen: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(successors[node])
        for t in net.transitions:
            if not any(net.enabled(_as_marking(markings[n]), t) for n in seen):
                return False
    return True


@settings(max_examples=40, deadline=None)
@given(net=small_net_strategy())
def test_verdict_consistent_with_independent_checks(net: PetriNet) -> None:
    """Random bounded net: verdict is one of the three classes and agrees with
    the independent L4 / DAG checks."""
    structure = _build_or_skip(net)
    report = analyze(net, structure)
    assert report.verdict in {"живая", "тупиковая", "частичнотупиковая"}
    if _strongly_live(net, structure):
        expected = "живая"
    elif _is_dag(structure):
        expected = "тупиковая"
    else:
        expected = "частичнотупиковая"
    assert report.verdict == expected
    assert verdict(structure, report) == expected


@settings(max_examples=40, deadline=None)
@given(net=small_net_strategy())
def test_conservative_consistent_random(net: PetriNet) -> None:
    """Random bounded net: report.conservative re-derives from the arcs and
    node sums independently."""
    structure = _build_or_skip(net)
    report = analyze(net, structure)
    info = report.conservative
    assert info == conservative(net, structure)
    per = info["per_transition"]
    for i, t in enumerate(net.transitions):
        assert per[t]["in"] == sum(w for _p, w in net.inputs[i])
        assert per[t]["out"] == sum(w for _p, w in net.outputs[i])
        assert per[t]["equal"] is (per[t]["in"] == per[t]["out"])
    totals = {sum(_as_marking(m)) for _nid, m in structure.nodes}
    constant = len(totals) <= 1
    balanced = all(entry["equal"] for entry in per.values())
    assert info["constant_sum"] == constant
    assert info["conservative"] == (balanced and constant)
