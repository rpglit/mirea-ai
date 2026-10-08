"""Reachability tests for the v2 model extensions.

Inhibitor arcs in BFS (via core.enabled) and in the Karp-Miller tree
(omega / positive natural blocks forever), priorities leaving the reachable
set unchanged, and the 422 guards for delayed/colored nets (ARCH section 2.3).
Round-1 anchors (1503/4983 smoke graph, single omega node) stay green in
test_reachability.py and are re-asserted here for the smoke anchor only.
"""

from __future__ import annotations

import pytest
from conftest import smoke_net
from hypothesis import given, settings
from hypothesis import strategies as st

from petrinet.core import Colors, PetriNet
from petrinet.errors import CapExceededError, UnsupportedModelError
from petrinet.reachability import build


def _net(**overrides: object) -> PetriNet:
    """A small 2-transition net: t1 {a,i}->{i,k}, t2 {i}->{k}, mu=(2,1,0)."""
    base: dict[str, object] = {
        "places": ("a", "i", "k"),
        "transitions": ("t1", "t2"),
        "inputs": ((("a", 1), ("i", 1)), (("i", 1),)),
        "outputs": ((("i", 1), ("k", 1)), (("k", 1),)),
        "initial_marking": (2, 1, 0),
    }
    base.update(overrides)
    return PetriNet(**base)  # type: ignore[arg-type]


def test_smoke_anchor_unchanged() -> None:
    """Round-1 anchor (D-009): 1503 nodes / 4983 edges on the smoke net."""
    structure = build(smoke_net(), "auto")
    assert structure.kind == "graph"
    assert structure.stats == {"nodes": 1503, "edges": 4983}


def test_inhibitor_reduces_reachable_set() -> None:
    """t2 is inhibited by a: while a holds a token t2 cannot fire."""
    plain_marks = {m for _, m in build(_net(), "bounded").nodes}
    inh_marks = {m for _, m in build(_net(inhibitors=((), ("a",))), "bounded").nodes}
    assert inh_marks == {(2, 1, 0), (1, 1, 1), (0, 1, 2), (0, 0, 3)}
    assert plain_marks != inh_marks
    # without the inhibitor t2 fired while a still held 2 tokens:
    assert (2, 0, 1) in plain_marks and (2, 0, 1) not in inh_marks


def test_karp_miller_omega_blocks_inhibitor_forever() -> None:
    """k grows without bound (t2 keeps i); omega in k blocks t3 forever.

    Net: t1 {i,f}->{i,k} (one-shot starter, consumes f); t2 {i}->{i,k}
    (counter); t3 {i}->{b} inhibited by k. mu=(i=1, f=1, k=0, b=0).
    Standard KM (ADR-0002): t3 fires once while k == 0 (node n2, terminal:
    it consumes the only i), then t2's growth promotes the root and the t1
    child to omega in k — from those nodes t3 can never depart again.
    """
    net = PetriNet(
        places=("i", "f", "k", "b"),
        transitions=("t1", "t2", "t3"),
        inputs=((("i", 1), ("f", 1)), (("i", 1),), (("i", 1),)),
        outputs=((("i", 1), ("k", 1)), (("i", 1), ("k", 1)), (("b", 1),)),
        initial_marking=(1, 1, 0, 0),
        inhibitors=((), (), ("k",)),
    )
    structure = build(net, "coverability")
    marks = {m for _, m in structure.nodes}
    # k grows without bound (t2 keeps i): root and the t1-child carry omega
    # in k; the one-shot t3 firing (possible while k == 0) is kept as a node.
    assert marks == {(1, 1, None, 0), (1, 0, None, 0), (0, 1, 0, 1)}
    assert structure.stats == {"nodes": 3, "edges": 2}
    # the only t3 edge leaves the root: it was recorded from the root's
    # pop-time label (k == 0) before t2's growth promoted the root to omega
    # (standard KM bookkeeping, ADR-0002). From the t1-child n1, whose label
    # holds omega in k at expansion time, t3 can never depart:
    t3_edges = [(s, d) for s, t, d in structure.edges if t == "t3"]
    assert t3_edges == [("n0", "n2")]
    assert not any(s == "n1" and t == "t3" for s, t, _ in structure.edges)
    # n2 is terminal (t3 consumed the only i)
    assert not any(s == "n2" for s, _, _ in structure.edges)


def test_delays_rejected_in_all_modes() -> None:
    net = _net(delays=((), (("k", 2),)))
    for mode in ("auto", "bounded", "coverability"):
        with pytest.raises(UnsupportedModelError):
            build(net, mode)  # type: ignore[arg-type]


def test_colors_rejected_in_all_modes() -> None:
    net = _net(
        colors=Colors(
            initial_values={"a": ["red"]}, guards={}, output_exprs={}
        )
    )
    for mode in ("auto", "bounded", "coverability"):
        with pytest.raises(UnsupportedModelError):
            build(net, mode)  # type: ignore[arg-type]


def test_priorities_do_not_change_reachability() -> None:
    plain = {m for _, m in build(_net(), "bounded").nodes}
    with_pr = {m for _, m in build(_net(priorities=(1, 0)), "bounded").nodes}
    assert plain == with_pr


@given(data=st.data())
@settings(max_examples=60, deadline=None)
def test_bfs_edges_consistent_with_core(data: st.DrawFn) -> None:
    """Random v2 nets: every BFS edge is an enabled firing (core semantics)."""
    n = data.draw(st.integers(2, 4))
    m = data.draw(st.integers(1, 3))
    places = tuple(f"p{i}" for i in range(n))
    transitions = tuple(f"t{j}" for j in range(m))
    def _arc_set() -> tuple[tuple[str, int], ...]:
        drawn = data.draw(
            st.lists(st.sampled_from(places), unique=True, min_size=0, max_size=n)
        )
        return tuple((p, 1) for p in drawn)

    inputs = tuple(_arc_set() for _ in range(m))
    outputs = tuple(_arc_set() for _ in range(m))
    initial_marking = tuple(data.draw(st.integers(0, 2)) for _ in range(n))

    def _place_set() -> tuple[str, ...]:
        return tuple(
            data.draw(st.lists(st.sampled_from(places), unique=True, min_size=0, max_size=n))
        )

    inhibitors = tuple(_place_set() for _ in range(m))
    net = PetriNet(
        places=places,
        transitions=transitions,
        inputs=inputs,  # type: ignore[arg-type]
        outputs=outputs,  # type: ignore[arg-type]
        initial_marking=initial_marking,  # type: ignore[arg-type]
        inhibitors=inhibitors if any(inhibitors) else None,  # type: ignore[arg-type]
    )
    try:
        structure = build(net, "bounded", cap=5000)
    except CapExceededError:
        return  # unbounded random net: the cap is a valid safety outcome
    by_id = {node_id: marking for node_id, marking in structure.nodes}
    assert by_id["n0"] == net.initial_marking
    for src, t, dst in structure.edges:
        assert net.enabled(by_id[src], t)
        assert net.fire(by_id[src], t) == by_id[dst]
