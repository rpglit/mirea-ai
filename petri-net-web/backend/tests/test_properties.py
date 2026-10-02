"""Unit and property tests for petrinet.properties (FR-007..FR-014, D-009..D-013, D-035)."""

from __future__ import annotations

from conftest import smoke_net
from hypothesis import assume, given, settings
from test_reachability import counter_net, cyclic50_net, mutex_net, small_net_strategy

from petrinet.core import Marking, PetriNet
from petrinet.errors import CapExceededError
from petrinet.properties import analyze, is_coverable, is_reachable
from petrinet.reachability import ReachableStructure, build

# D-011 deadlock list in D-022 canonical (lexicographic) order; 23 distinct markings.
FROZEN_DEADLOCKS: tuple[Marking, ...] = (
    (0, 0, 0, 0, 1, 10),
    (0, 0, 1, 5, 0, 9),
    (0, 0, 2, 17, 1, 6),
    (0, 0, 3, 7, 1, 7),
    (0, 0, 3, 22, 0, 5),
    (0, 0, 4, 12, 0, 6),
    (0, 0, 5, 2, 0, 7),
    (0, 0, 5, 24, 1, 3),
    (0, 0, 6, 14, 1, 4),
    (0, 0, 6, 29, 0, 2),
    (0, 0, 7, 4, 1, 5),
    (0, 0, 7, 19, 0, 3),
    (0, 0, 8, 9, 0, 4),
    (0, 0, 9, 21, 1, 1),
    (0, 0, 10, 11, 1, 2),
    (0, 0, 10, 26, 0, 0),
    (0, 0, 11, 1, 1, 3),
    (0, 0, 11, 16, 0, 1),
    (0, 0, 12, 6, 0, 2),
    (0, 0, 14, 8, 1, 0),
    (0, 0, 16, 3, 0, 0),
    (1, 0, 11, 18, 1, 0),
    (1, 0, 13, 13, 0, 0),
)


def _build_or_skip(net: PetriNet) -> ReachableStructure:
    """Build the auto graph with a small cap; skip unbounded examples (fast)."""
    try:
        return build(net, "auto", cap=3000)
    except CapExceededError:
        assume(False)


def test_smoke_report_exact() -> None:
    """Full smoke report matches D-009..D-013 and D-035 (deadlocks in D-022 order)."""
    net = smoke_net()
    report = analyze(net, build(net, "auto"))
    assert [report.per_place_k[p] for p in net.places] == [10, 8, 16, 29, 8, 10]
    assert report.global_k == 29
    assert report.bounded is True
    assert report.safe is False
    assert report.liveness.level == "L1"
    for t in net.transitions:
        entry = report.liveness.transitions[t]
        assert entry.occurs is True
        assert entry.level == "L1"
    assert len(report.deadlocks) == 23
    assert report.deadlocks == sorted(report.deadlocks)
    assert set(report.deadlocks) == set(FROZEN_DEADLOCKS)
    assert report.dead_transitions == []
    assert report.home_state is False
    assert report.deadlock_free is False
    assert report.approximation is None
    assert report.stats == {"nodes": 1503, "edges": 4983}


def test_smoke_queries() -> None:
    """FR-010 anchors on the smoke graph: reachability and coverability queries.

    The joint per-place maximum (10, 8, 16, 29, 8, 10) is NOT coverable: the D-010
    maxima are achieved in different markings (the graph is a DAG, D-035), so no
    reachable marking reaches them all at once.
    """
    net = smoke_net()
    graph = build(net, "auto")
    assert is_reachable(net, graph, (7, 4, 2, 5, 4, 3)) is True
    assert is_reachable(net, graph, (5, 5, 2, 5, 4, 3)) is True
    assert is_reachable(net, graph, (11, 0, 0, 0, 0, 0)) is False
    assert is_reachable(net, graph, (0, 0, 0, 0, 1, 10)) is True
    assert is_coverable(net, graph, (0, 0, 0, 0, 0, 0)) is True
    assert is_coverable(net, graph, (7, 4, 2, 5, 4, 3)) is True
    assert is_coverable(net, graph, (11, 0, 0, 0, 0, 0)) is False
    assert is_coverable(net, graph, (10, 8, 16, 29, 8, 10)) is False


def test_counter_coverability_report() -> None:
    """Counter tree (5.6): omega p1, unbounded/not safe, t1 L4, no deadlocks.

    t1 is L4 without a cycle: omega-enabled at the single tree node whose backwards
    closure covers all; home state false (the node is (omega,), not mu0); the
    coverability tree answers exact reachability with None.
    """
    net = counter_net()
    tree = build(net, "coverability")
    report = analyze(net, tree)
    assert report.per_place_k == {"p1": None}
    assert report.global_k is None
    assert report.bounded is False
    assert report.safe is False
    assert report.liveness.level == "L4"
    entry = report.liveness.transitions["t1"]
    assert entry.occurs is True
    assert entry.level == "L4"
    assert report.deadlocks == []
    assert report.deadlock_free is True
    assert report.home_state is False
    assert report.approximation == "omega"
    assert is_reachable(net, tree, (1,)) is None
    assert is_coverable(net, tree, (1,)) is True
    assert is_coverable(net, tree, (0,)) is True


def test_mutex_report() -> None:
    """Mutex net: safe (all k_p = 1), all four transitions L4, home state true."""
    net = mutex_net()
    report = analyze(net, build(net, "auto"))
    assert report.liveness.level == "L4"
    for t in net.transitions:
        entry = report.liveness.transitions[t]
        assert entry.occurs is True
        assert entry.level == "L4"
    assert report.per_place_k == {"p0": 1, "p1": 1, "p2": 1}
    assert report.safe is True
    assert report.home_state is True
    assert report.deadlock_free is True
    assert report.deadlocks == []
    assert report.approximation is None


def test_cyclic50_report() -> None:
    """Cyclic 5.4 fixture: 25 nodes / 25 edges, L4, safe, home, deadlock-free."""
    net = cyclic50_net()
    graph = build(net, "auto")
    report = analyze(net, graph)
    assert graph.stats == {"nodes": 25, "edges": 25}
    assert report.liveness.level == "L4"
    assert report.safe is True
    assert report.home_state is True
    assert report.deadlock_free is True


def test_l0_l1_mix_net() -> None:
    """L0/live mix (ADR-0004 example 4): t3 dead (L0), t1/t2 live (L4), net L0.

    t1/t2 are L4, not merely L3: every reachable marking reaches their enablement,
    and the ADR-0004 classification runs the L4 closure test before the cycle test.
    """
    net = PetriNet(
        places=("p1", "p2"),
        transitions=("t1", "t2", "t3"),
        inputs=((("p1", 1),), (("p2", 1),), (("p1", 1), ("p2", 1))),
        outputs=((("p2", 1),), (("p1", 1),), (("p1", 1),)),
        initial_marking=(1, 0),
    )
    report = analyze(net, build(net, "auto"))
    assert report.liveness.transitions["t3"].occurs is False
    assert report.liveness.transitions["t3"].level == "L0"
    assert report.liveness.transitions["t1"].level == "L4"
    assert report.liveness.transitions["t2"].level == "L4"
    assert report.liveness.level == "L0"
    assert report.dead_transitions == ["t3"]
    assert report.deadlocks == []
    assert report.home_state is True


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_report_deterministic(net: PetriNet) -> None:
    """Two independent builds of the same net give equal Report objects."""
    first = _build_or_skip(net)
    second = _build_or_skip(net)
    assert analyze(net, first) == analyze(net, second)


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_safety_implies_bounded(net: PetriNet) -> None:
    """A safe report is always bounded (every k_p <= 1)."""
    report = analyze(net, _build_or_skip(net))
    assert not report.safe or report.bounded


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_l4_implies_deadlock_free(net: PetriNet) -> None:
    """A net-level L4 report is deadlock-free."""
    report = analyze(net, _build_or_skip(net))
    assert report.liveness.level != "L4" or report.deadlock_free


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_level_never_l2(net: PetriNet) -> None:
    """Per-transition levels are never 'L2'; the net level is the min by rank."""
    report = analyze(net, _build_or_skip(net))
    rank = {"L0": 0, "L1": 1, "L3": 3, "L4": 4}
    levels = [entry.level for entry in report.liveness.transitions.values()]
    for level in levels:
        assert level in rank
    assert rank[report.liveness.level] == min(rank[level] for level in levels)


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_deadlocks_consistent_with_active(net: PetriNet) -> None:
    """Reported deadlocks are exactly the graph nodes where net.active(m) == []."""
    graph = _build_or_skip(net)
    report = analyze(net, graph)
    markings: set[Marking] = set()
    for _nid, raw in graph.nodes:
        values: list[int] = []
        for value in raw:
            assert value is not None
            values.append(value)
        markings.add(tuple(values))
    derived = {m for m in markings if net.active(m) == []}
    assert set(report.deadlocks) == derived
