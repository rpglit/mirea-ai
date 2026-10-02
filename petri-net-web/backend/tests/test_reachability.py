"""Unit and property tests for petrinet.reachability (D-009, D-034 anchors)."""

from __future__ import annotations

from collections import deque

import pytest
from conftest import smoke_net
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from petrinet.core import Marking, PetriNet
from petrinet.errors import CapExceededError
from petrinet.reachability import ReachableStructure, build


def counter_net() -> PetriNet:
    """Unbounded counter (REQUIREMENTS 5.6): t1 adds one token to p1 forever."""
    return PetriNet(
        places=("p1",),
        transitions=("t1",),
        inputs=((),),
        outputs=((("p1", 1),),),
        initial_marking=(1,),
    )


def mutex_net() -> PetriNet:
    """Mutex net: one token moves p0 -> p1 -> p0 and p0 -> p2 -> p0 (1-bounded)."""
    return PetriNet(
        places=("p0", "p1", "p2"),
        transitions=("t1", "t2", "t3", "t4"),
        inputs=(
            (("p0", 1),),
            (("p1", 1),),
            (("p0", 1),),
            (("p2", 1),),
        ),
        outputs=(
            (("p1", 1),),
            (("p0", 1),),
            (("p2", 1),),
            (("p0", 1),),
        ),
        initial_marking=(1, 0, 0),
    )


def cyclic50_net() -> PetriNet:
    """50-node cyclic net (REQUIREMENTS 5.4): the token cycles p1 -> ... -> p25 -> p1."""
    n = 25
    places = tuple(f"p{i}" for i in range(1, n + 1))
    transitions = tuple(f"t{i}" for i in range(1, n + 1))
    inputs = tuple(((places[i - 1], 1),) for i in range(n))
    outputs = tuple(((places[i % n], 1),) for i in range(n))
    return PetriNet(
        places=places,
        transitions=transitions,
        inputs=inputs,
        outputs=outputs,
        initial_marking=(1,) + (0,) * (n - 1),
    )


def _concrete_markings(graph: ReachableStructure) -> dict[str, Marking]:
    """Map node id -> concrete marking; a 'graph' structure never holds omega."""
    markings: dict[str, Marking] = {}
    for node_id, raw in graph.nodes:
        values: list[int] = []
        for value in raw:
            if value is None:
                raise AssertionError(f"omega in graph node {node_id}")
            values.append(value)
        markings[node_id] = tuple(values)
    return markings


@st.composite
def small_net_strategy(draw: DrawFn) -> PetriNet:
    """Draw a random small net: 1-3 places, 1-3 transitions, weights 1-2, marking 0-3."""
    n_places = draw(st.integers(min_value=1, max_value=3))
    n_transitions = draw(st.integers(min_value=1, max_value=3))
    places = tuple(f"p{i}" for i in range(n_places))
    transitions = tuple(f"t{i}" for i in range(n_transitions))
    arcs = st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=n_places - 1),
            st.integers(min_value=1, max_value=2),
        ),
        min_size=0,
        max_size=n_places,
        unique_by=lambda arc: arc[0],
    )
    inputs = tuple(tuple((places[p], w) for p, w in draw(arcs)) for _ in range(n_transitions))
    outputs = tuple(tuple((places[p], w) for p, w in draw(arcs)) for _ in range(n_transitions))
    marking_values = draw(
        st.lists(st.integers(min_value=0, max_value=3), min_size=n_places, max_size=n_places)
    )
    return PetriNet(
        places=places,
        transitions=transitions,
        inputs=inputs,
        outputs=outputs,
        initial_marking=tuple(marking_values),
    )


def test_smoke_graph_exact() -> None:
    """Smoke graph matches D-009: 1503 nodes / 4983 edges in deterministic BFS order."""
    graph = build(smoke_net(), "auto")
    assert graph.kind == "graph"
    assert graph.stats == {"nodes": 1503, "edges": 4983}
    assert graph.nodes[0] == ("n0", (7, 4, 2, 5, 4, 3))
    assert [node_id for node_id, _ in graph.nodes] == [f"n{i}" for i in range(1503)]
    assert graph.nodes[:3] == [
        ("n0", (7, 4, 2, 5, 4, 3)),
        ("n1", (5, 5, 2, 5, 4, 3)),
        ("n2", (6, 4, 4, 5, 4, 2)),
    ]
    assert graph.edges[:3] == [("n0", "t1", "n1"), ("n0", "t2", "n2"), ("n0", "t3", "n3")]


def test_smoke_bounded_mode_same() -> None:
    """Modes 'auto' and 'bounded' build the identical smoke reachability graph."""
    auto = build(smoke_net(), "auto")
    bounded = build(smoke_net(), "bounded")
    assert bounded.kind == "graph"
    assert auto.nodes == bounded.nodes
    assert auto.edges == bounded.edges


def test_counter_cap() -> None:
    """The unbounded counter overflows the cap: CapExceededError carries the limit."""
    with pytest.raises(CapExceededError) as excinfo:
        build(counter_net(), "auto", cap=1000)
    assert excinfo.value.limit == 1000


def test_counter_coverability_single_omega() -> None:
    """The counter's coverability tree is a single omega node (D-034: cap never hit)."""
    tree = build(counter_net(), "coverability")
    assert tree.kind == "coverability"
    assert tree.nodes == [("n0", (None,))]
    assert tree.edges == []


def test_mutex_bounded() -> None:
    """The mutex net has 3 markings / 4 edges and is 1-bounded."""
    graph = build(mutex_net(), "auto")
    assert graph.stats == {"nodes": 3, "edges": 4}
    for _, marking in graph.nodes:
        assert all(value is not None and value <= 1 for value in marking)


def test_mutex_coverability_no_omega() -> None:
    """A bounded net's coverability tree never promotes omega."""
    tree = build(mutex_net(), "coverability")
    assert all(value is not None for _, marking in tree.nodes for value in marking)


def test_cyclic50() -> None:
    """The 50-node cyclic net gives 25 safe markings n0..n24 with 25 edges."""
    graph = build(cyclic50_net(), "auto")
    assert graph.stats == {"nodes": 25, "edges": 25}
    assert [node_id for node_id, _ in graph.nodes] == [f"n{i}" for i in range(25)]
    for _, marking in graph.nodes:
        assert all(value is not None and value <= 1 for value in marking)


def test_smoke_coverability_capped() -> None:
    """D-034: the bounded smoke net's tree blows up past the default cap."""
    with pytest.raises(CapExceededError):
        build(smoke_net(), "coverability", cap=50000)


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_graph_edges_are_legal_firings(net: PetriNet) -> None:
    """Every graph edge labels a legal firing: t enabled at src, fire(src, t) == dst.

    Examples whose state space exceeds the test cap are rejected via assume.
    """
    try:
        graph = build(net, "auto", cap=1000)
    except CapExceededError:
        assume(False)
    markings = _concrete_markings(graph)
    for src_id, transition, dst_id in graph.edges:
        assert net.enabled(markings[src_id], transition)
        assert net.fire(markings[src_id], transition) == markings[dst_id]


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_graph_nodes_reachable_from_root(net: PetriNet) -> None:
    """Every node n<index> lies on a path of firing edges from the root n0 (BFS).

    Examples whose state space exceeds the test cap are rejected via assume.
    """
    try:
        graph = build(net, "auto", cap=1000)
    except CapExceededError:
        assume(False)
    adjacency: dict[str, list[str]] = {}
    for src_id, _, dst_id in graph.edges:
        adjacency.setdefault(src_id, []).append(dst_id)
    seen: set[str] = {"n0"}
    queue: deque[str] = deque(["n0"])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    for index, (node_id, _) in enumerate(graph.nodes):
        assert node_id == f"n{index}"
        assert node_id in seen


@settings(max_examples=60, deadline=None)
@given(net=small_net_strategy())
def test_omega_only_in_coverability_kind(net: PetriNet) -> None:
    """Coverability builds report kind 'coverability' with root node n0.

    Examples whose tree exceeds the test cap (D-034 blow-up) are rejected via assume.
    """
    try:
        tree = build(net, "coverability", cap=2000)
    except CapExceededError:
        assume(False)
    assert tree.kind == "coverability"
    assert tree.nodes[0][0] == "n0"
