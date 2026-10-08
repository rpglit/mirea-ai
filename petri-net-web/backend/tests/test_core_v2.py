"""Unit and property tests for the PetriNet v2 core (ADR-0009).

Covers the extended model: inhibitor arcs (⊣), priorities (Pr t), parallel
firing (fire_set), incidence matrices (M7) and minimal markings (M6), plus
the colored layer (data only, A-21). Round-1 compatibility stays green via
the untouched test_core.py.
"""

from __future__ import annotations

import dataclasses

import pytest
from conftest import smoke_net
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from petrinet.core import (
    Colors,
    Marking,
    PetriNet,
    active,
    enabled,
    fire,
    fire_set,
    incidence,
    minimal_marking,
)
from petrinet.errors import ConflictError, TransitionNotEnabledError


def pn07_net() -> PetriNet:
    """TASK-PN-07 (seminar 1, example 2): I(t1)={p1,p1,p2}, I(t2)={p1,p2,p2}, O={p3} for both."""
    return PetriNet(
        places=("p1", "p2", "p3"),
        transitions=("t1", "t2"),
        inputs=((("p1", 2), ("p2", 1)), (("p1", 1), ("p2", 2))),
        outputs=((("p3", 1),), (("p3", 1),)),
        initial_marking=(2, 2, 0),
    )


def pn09_net() -> PetriNet:
    """TASK-PN-09 (seminar 2, task 5): 5x4 net, mu_min = (2, 2, 1, 2, 2)."""
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


def pn35_net() -> PetriNet:
    """TASK-PN-35 (seminar 5, example 1): p1->t1, t1->p2, t1->p3, p2->t2, p3->t2, t2->p1, t2->p4."""
    return PetriNet(
        places=("p1", "p2", "p3", "p4"),
        transitions=("t1", "t2"),
        inputs=((("p1", 1),), (("p2", 1), ("p3", 1))),
        outputs=((("p2", 1), ("p3", 1)), (("p1", 1), ("p4", 1))),
        initial_marking=(1, 0, 2, 1),
    )


def inhibitor_net() -> PetriNet:
    """t needs one token in p1 and is inhibited by p2 (weight-1 arc p2⊣t)."""
    return PetriNet(
        places=("p1", "p2"),
        transitions=("t",),
        inputs=((("p1", 1),),),
        outputs=((("p2", 1),),),
        initial_marking=(1, 0),
        inhibitors=(("p2",),),
    )


def priority_net() -> PetriNet:
    """t1 and t2 conflict over p1 (t1 needs 2 tokens, t2 needs 1); t3 is independent."""
    return PetriNet(
        places=("p1", "p2", "p3", "p4"),
        transitions=("t1", "t2", "t3"),
        inputs=(
            (("p1", 2),),
            (("p1", 1),),
            (("p4", 1),),
        ),
        outputs=(
            (("p2", 1),),
            (("p3", 1),),
            (("p4", 1),),
        ),
        initial_marking=(1, 0, 0, 1),
    )


# --- inhibitors (M2⊣) -------------------------------------------------------


def test_inhibitor_blocks_when_place_has_tokens() -> None:
    """A weight-1 inhibitor arc blocks the transition while the place holds >= 1 token."""
    net = inhibitor_net()
    assert enabled(net, (1, 0), "t") is True
    assert enabled(net, (1, 1), "t") is False
    assert enabled(net, (1, 3), "t") is False


def test_inhibitor_released_when_place_empty() -> None:
    """At 0 tokens in the inhibitor place the transition is enabled and fires again."""
    net = inhibitor_net()
    assert net.enabled((1, 0), "t") is True
    assert fire(net, (1, 0), "t") == (0, 1)
    with pytest.raises(TransitionNotEnabledError):
        fire(net, (1, 1), "t")


def test_inhibitor_respects_usable_vector() -> None:
    """τ-semantics: the inhibitor checks the usable (available now) tokens, not m."""
    net = inhibitor_net()
    # The p2 token exists but is still in a τ-delay: usable = (1, 0).
    assert enabled(net, (1, 1), "t", usable=(1, 0)) is True
    assert enabled(net, (1, 1), "t", usable=(1, 1)) is False
    # The input-arc part is checked against m, not usable:
    assert enabled(net, (0, 1), "t", usable=(0, 0)) is False


def test_active_inhibitor() -> None:
    """active() drops inhibitor-blocked transitions."""
    net = inhibitor_net()
    assert net.active((1, 1)) == []
    assert net.active((1, 0)) == ["t"]


# --- priorities (M8) ---------------------------------------------------------


def test_priorities_conflict_group_keeps_max() -> None:
    """In a conflict group only the transition with the maximal Pr t stays active."""
    net = priority_net()
    assert net.active((2, 0, 0, 0)) == ["t1", "t2"]  # no priorities -> both
    high_t1 = dataclasses.replace(net, priorities=(1, 0, 0))
    assert high_t1.active((2, 0, 0, 0)) == ["t1"]
    high_t2 = dataclasses.replace(net, priorities=(0, 1, 0))
    assert high_t2.active((2, 0, 0, 0)) == ["t2"]


def test_priorities_tie_keeps_all() -> None:
    """Equal Pr t inside a conflict group keeps every transition."""
    net = dataclasses.replace(priority_net(), priorities=(1, 1, 0))
    assert net.active((2, 0, 0, 0)) == ["t1", "t2"]


def test_priorities_independent_transition_kept() -> None:
    """A non-conflicting enabled transition survives even with the lowest Pr t."""
    net = dataclasses.replace(priority_net(), priorities=(5, 4, 0))
    assert net.active((2, 0, 0, 1)) == ["t1", "t3"]


def test_priorities_disabled_transition_ignored() -> None:
    """A disabled transition does not suppress a conflicting lower-priority one."""
    net = dataclasses.replace(priority_net(), priorities=(5, 1, 0))
    # p1 holds 1 token: t1 (needs 2) is disabled, t2 (needs 1) is enabled.
    assert net.active((1, 0, 0, 0)) == ["t2"]


def test_priorities_transitive_conflict_group() -> None:
    """Conflict groups are transitive: t1~t2~t3 via shared places, maximal Pr wins."""
    net = PetriNet(
        places=("p1", "p2", "p3", "p4"),
        transitions=("t1", "t2", "t3"),
        inputs=(
            (("p1", 1),),
            (("p1", 1), ("p2", 1)),
            (("p2", 1),),
        ),
        outputs=(
            (("p3", 1),),
            (("p3", 1),),
            (("p4", 1),),
        ),
        initial_marking=(1, 1, 0, 0),
        priorities=(5, 0, 5),
    )
    # t1 and t3 share no place, but both conflict with t2: one group
    # {t1, t2, t3}, maximal Pr = 5 -> t1 and t3.
    assert net.active((1, 1, 0, 0)) == ["t1", "t3"]


# --- fire_set (parallel firing) ----------------------------------------------


def test_fire_set_parallel_success() -> None:
    """A non-conflicting enabled set fires as one summed application."""
    net = PetriNet(
        places=("p1", "p2", "p3", "p4"),
        transitions=("t1", "t2"),
        inputs=((("p1", 1),), (("p2", 1),)),
        outputs=((("p3", 1),), (("p4", 1),)),
        initial_marking=(1, 1, 0, 0),
    )
    assert fire_set(net, (1, 1, 0, 0), ["t1", "t2"]) == (0, 0, 1, 1)
    sequential = fire(net, fire(net, (1, 1, 0, 0), "t1"), "t2")
    assert fire_set(net, (1, 1, 0, 0), ["t1", "t2"]) == sequential


def test_fire_set_conflict_raises() -> None:
    """Two transitions sharing an input place conflict -> ConflictError with the place."""
    net = priority_net()
    with pytest.raises(ConflictError) as excinfo:
        fire_set(net, (2, 0, 0, 0), ["t1", "t2"])
    error = excinfo.value
    assert error.transitions == ("t1", "t2")
    assert error.place == "p1"
    assert "конфликт" in str(error)
    assert "p1" in str(error)


def test_fire_set_disabled_member_raises() -> None:
    """A disabled transition in the set -> ConflictError naming exactly that transition."""
    net = priority_net()
    with pytest.raises(ConflictError) as excinfo:
        fire_set(net, (1, 0, 0, 0), ["t1", "t2"])
    error = excinfo.value
    assert error.transitions == ("t1",)
    assert error.place is None
    assert "конфликт" in str(error)


def test_fire_set_empty() -> None:
    """The empty set is vacuously conflict-free and changes nothing."""
    net = priority_net()
    assert fire_set(net, (1, 0, 0, 0), []) == (1, 0, 0, 0)


# --- incidence (M7) -----------------------------------------------------------


def test_incidence_smoke_net() -> None:
    """W−/W+/W of the 6x5 reference net (TASK-PN-05) match its arc data."""
    net = smoke_net()
    w_minus, w_plus, w = incidence(net)
    assert w_minus == [
        [2, 1, 0, 0, 0],
        [0, 0, 1, 1, 0],
        [0, 0, 0, 1, 0],
        [0, 0, 0, 2, 0],
        [0, 0, 0, 0, 2],
        [0, 1, 0, 0, 0],
    ]
    assert w_plus == [
        [0, 0, 0, 0, 1],
        [1, 0, 0, 0, 0],
        [0, 2, 0, 0, 1],
        [0, 0, 3, 0, 0],
        [0, 0, 0, 1, 0],
        [0, 0, 0, 1, 0],
    ]
    assert w == [
        [-2, -1, 0, 0, 1],
        [1, 0, -1, -1, 0],
        [0, 2, 0, -1, 1],
        [0, 0, 3, -2, 0],
        [0, 0, 0, 1, -2],
        [0, -1, 0, 1, 0],
    ]
    # M7 cross-check (TASK-PN-05): sigma = t1..t5, v = (1,1,1,1,1),
    # mu' = mu + W·v = (5, 3, 4, 6, 3, 3).
    mu = net.initial_marking
    v = [1, 1, 1, 1, 1]
    expected = [mu[i] + sum(w[i][j] * v[j] for j in range(5)) for i in range(6)]
    assert expected == [5, 3, 4, 6, 3, 3]


def test_incidence_pn35_matrices() -> None:
    """W−/W+/W of TASK-PN-35 equal the matrices quoted in the seminar material."""
    net = pn35_net()
    w_minus, w_plus, w = incidence(net)
    assert w_minus == [[1, 0], [0, 1], [0, 1], [0, 0]]
    assert w_plus == [[0, 1], [1, 0], [1, 0], [0, 1]]
    assert w == [[-1, 1], [1, -1], [1, -1], [0, 1]]


# --- minimal marking (M6) ------------------------------------------------------


def test_minimal_marking_pn07() -> None:
    """TASK-PN-07: component-wise max (2,2,0); parallel sum (3,3,0)."""
    net = pn07_net()
    assert minimal_marking(net) == (2, 2, 0)
    assert minimal_marking(net, parallel=True) == (3, 3, 0)
    for t in ("t1", "t2"):
        assert net.enabled(minimal_marking(net), t)
        assert net.enabled(minimal_marking(net, parallel=True), t)


def test_minimal_marking_pn09() -> None:
    """TASK-PN-09: mu_min = (2, 2, 1, 2, 2) and it enables all t1..t4."""
    net = pn09_net()
    mu_min = minimal_marking(net)
    assert mu_min == (2, 2, 1, 2, 2)
    assert all(net.enabled(mu_min, t) for t in net.transitions)


# --- model compatibility / colors (A-21) ---------------------------------------


def test_new_fields_default_none() -> None:
    """Round-1 constructors: all v2 fields default to None (classical net)."""
    net = smoke_net()
    assert net.inhibitors is None
    assert net.priorities is None
    assert net.delays is None
    assert net.colors is None
    # Free-function API agrees with the round-1 methods (smoke anchor, D-014).
    assert active(net, net.initial_marking) == ["t1", "t2", "t3", "t4", "t5"]
    assert enabled(net, net.initial_marking, "t1") is True
    assert fire(net, net.initial_marking, "t1") == (5, 5, 2, 5, 4, 3)


def test_colors_layer_is_data_only() -> None:
    """The colored layer (A-21) is stored verbatim; classical semantics are unchanged."""
    colors = Colors(
        initial_values={"p1": ["a", "b"]},
        guards={"t1": ["v - 1"]},
        output_exprs={"t1": ["v"]},
    )
    net = dataclasses.replace(
        smoke_net(), colors=colors, delays=((), (("p3", 2),), (), (), ())
    )
    assert net.colors is colors
    assert net.delays == ((), (("p3", 2),), (), (), ())
    assert net.active(net.initial_marking) == ["t1", "t2", "t3", "t4", "t5"]
    assert net.fire(net.initial_marking, "t1") == (5, 5, 2, 5, 4, 3)


# --- property tests (hypothesis) -------------------------------------------------


@st.composite
def classical_net_with_marking(draw: DrawFn) -> tuple[PetriNet, Marking]:
    """Draw a random small classical net (no v2 fields) with a random marking."""
    n_places = draw(st.integers(min_value=1, max_value=4))
    n_transitions = draw(st.integers(min_value=1, max_value=4))
    places: tuple[str, ...] = tuple(f"p{i}" for i in range(n_places))
    transitions: tuple[str, ...] = tuple(f"t{i}" for i in range(n_transitions))
    arcs = st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=n_places - 1),
            st.integers(min_value=1, max_value=3),
        ),
        min_size=0,
        max_size=n_places,
        unique_by=lambda arc: arc[0],
    )
    inputs: list[tuple[tuple[str, int], ...]] = []
    outputs: list[tuple[tuple[str, int], ...]] = []
    for _ in range(n_transitions):
        inputs.append(tuple((places[place], weight) for place, weight in draw(arcs)))
        outputs.append(tuple((places[place], weight) for place, weight in draw(arcs)))
    marking = tuple(
        draw(st.lists(st.integers(min_value=0, max_value=5), min_size=n_places, max_size=n_places))
    )
    return (
        PetriNet(
            places=places,
            transitions=transitions,
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            initial_marking=marking,
        ),
        marking,
    )


@st.composite
def net_with_inhibitors(draw: DrawFn) -> tuple[PetriNet, Marking, Marking]:
    """Draw a random small net with random inhibitor arcs, a marking m and usable <= m."""
    n_places = draw(st.integers(min_value=1, max_value=4))
    n_transitions = draw(st.integers(min_value=1, max_value=4))
    places: tuple[str, ...] = tuple(f"p{i}" for i in range(n_places))
    transitions: tuple[str, ...] = tuple(f"t{i}" for i in range(n_transitions))
    arcs = st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=n_places - 1),
            st.integers(min_value=1, max_value=3),
        ),
        min_size=0,
        max_size=n_places,
        unique_by=lambda arc: arc[0],
    )
    inputs: tuple[tuple[tuple[str, int], ...], ...] = tuple(
        tuple((places[place], weight) for place, weight in draw(arcs)) for _ in range(n_transitions)
    )
    outputs: tuple[tuple[tuple[str, int], ...], ...] = tuple(
        tuple((places[place], weight) for place, weight in draw(arcs)) for _ in range(n_transitions)
    )
    inhibitor_places = st.lists(
        st.integers(min_value=0, max_value=n_places - 1), max_size=n_places, unique=True
    )
    inhibitors: tuple[tuple[str, ...], ...] = tuple(
        tuple(f"p{i}" for i in draw(inhibitor_places)) for _ in range(n_transitions)
    )
    marking = tuple(
        draw(st.lists(st.integers(min_value=0, max_value=5), min_size=n_places, max_size=n_places))
    )
    usable = tuple(draw(st.integers(min_value=0, max_value=value)) for value in marking)
    return (
        PetriNet(
            places=places,
            transitions=transitions,
            inputs=inputs,
            outputs=outputs,
            inhibitors=inhibitors,
            initial_marking=marking,
        ),
        marking,
        usable,
    )


@settings(max_examples=100)
@given(case=classical_net_with_marking())
def test_fire_set_equals_sequential_fires(case: tuple[PetriNet, Marking]) -> None:
    """A conflict-free enabled subset: parallel firing == firing it one by one."""
    net, m0 = case
    chosen: list[str] = []
    taken: set[str] = set()
    for i, t in enumerate(net.transitions):
        own = {place for place, _ in net.inputs[i]}
        if net.enabled(m0, t) and not (taken & own):
            chosen.append(t)
            taken |= own
    marking = m0
    for t in chosen:
        marking = net.fire(marking, t)
    assert fire_set(net, m0, chosen) == marking


@settings(max_examples=100)
@given(case=classical_net_with_marking())
def test_fire_set_single_equals_fire(case: tuple[PetriNet, Marking]) -> None:
    """A one-element set fires exactly like fire()."""
    net, m = case
    for t in net.transitions:
        if net.enabled(m, t):
            assert fire_set(net, m, [t]) == fire(net, m, t)


@settings(max_examples=100)
@given(case=net_with_inhibitors())
def test_enabled_default_implies_usable(case: tuple[PetriNet, Marking, Marking]) -> None:
    """With usable <= m: enabled at m implies enabled at (m, usable).

    An inhibitor place that is empty in m stays empty in any usable vector
    below m, and the input-arc part is checked against m in both forms.
    """
    net, m, usable = case
    for t in net.transitions:
        if net.enabled(m, t):
            assert net.enabled(m, t, usable=usable)


@settings(max_examples=100)
@given(case=classical_net_with_marking())
def test_enabled_monotone_in_marking(case: tuple[PetriNet, Marking]) -> None:
    """Classical enabledness is monotone: enabled at usable <= m implies enabled at m."""
    net, m = case
    usable = tuple(value // 2 for value in m)
    for t in net.transitions:
        if net.enabled(usable, t):
            assert net.enabled(m, t)


@settings(max_examples=100)
@given(case=classical_net_with_marking())
def test_minimal_marking_enables_every_transition(case: tuple[PetriNet, Marking]) -> None:
    """M6: the minimal marking (max and parallel sum) enables every transition."""
    net, _ = case
    for mu in (minimal_marking(net), minimal_marking(net, parallel=True)):
        for t in net.transitions:
            assert net.enabled(mu, t)


@settings(max_examples=100)
@given(case=classical_net_with_marking())
def test_incidence_reproduces_fire(case: tuple[PetriNet, Marking]) -> None:
    """W = W+ − W− element-wise, and for every fire: m' = m + W·e_t (one column)."""
    net, m = case
    w_minus, w_plus, w = incidence(net)
    for i in range(len(net.places)):
        for j in range(len(net.transitions)):
            assert w[i][j] == w_plus[i][j] - w_minus[i][j]
    for j, t in enumerate(net.transitions):
        if net.enabled(m, t):
            fired = fire(net, m, t)
            for i in range(len(net.places)):
                assert fired[i] == m[i] + w[i][j]
