"""Unit and property tests for petrinet.core (smoke anchors from D-014)."""

from __future__ import annotations

import dataclasses

import pytest
from conftest import smoke_net
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from petrinet.core import Marking, PetriNet
from petrinet.errors import TransitionNotEnabledError


@st.composite
def net_with_marking(draw: DrawFn) -> tuple[PetriNet, Marking]:
    """Draw a random small net (1..4 places, 1..4 transitions) with a random marking."""
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


def test_smoke_active_at_mu0() -> None:
    """All five transitions are active at mu0 (D-014)."""
    net = smoke_net()
    assert net.active(net.initial_marking) == ["t1", "t2", "t3", "t4", "t5"]


def test_smoke_fire_t1() -> None:
    """Firing t1 at mu0 gives (5, 5, 2, 5, 4, 3) (D-014)."""
    net = smoke_net()
    assert net.fire(net.initial_marking, "t1") == (5, 5, 2, 5, 4, 3)


def test_fire_disabled_raises() -> None:
    """Firing a disabled transition raises TransitionNotEnabledError with context."""
    net = smoke_net()
    zero = (0, 0, 0, 0, 0, 0)
    with pytest.raises(TransitionNotEnabledError) as excinfo:
        net.fire(zero, "t1")
    error = excinfo.value
    assert error.marking == zero
    assert error.transition == "t1"


def test_immutability() -> None:
    """mu0 survives fire() unchanged and the net itself is a frozen dataclass."""
    net = smoke_net()
    mu0 = net.initial_marking
    assert net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)
    assert mu0 == (7, 4, 2, 5, 4, 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        net.places = ("x",)  # type: ignore[misc]  # deliberate: frozen must reject writes


def test_empty_input_transition_always_enabled() -> None:
    """A transition with no input arcs is enabled at every marking, even (0,)."""
    net = PetriNet(
        places=("p1",),
        transitions=("t",),
        inputs=((),),
        outputs=((("p1", 1),),),
        initial_marking=(0,),
    )
    assert net.enabled((0,), "t") is True
    assert net.fire((0,), "t") == (1,)


def test_active_order_declared() -> None:
    """active() returns the enabled transitions in declared (t1..t5) order.

    Marking (1, 1, 1, 2, 0, 1), checked arc by arc against the smoke net:
      t1: needs p1 >= 2 -> p1 = 1, disabled;
      t2: needs p1 >= 1 and p6 >= 1 -> 1 >= 1 and 1 >= 1, enabled;
      t3: needs p2 >= 1 -> 1 >= 1, enabled;
      t4: needs p2 >= 1, p3 >= 1, p4 >= 2 -> 1, 1, 2, enabled;
      t5: needs p5 >= 2 -> p5 = 0, disabled.
    Note: t4 can never be enabled without t3 (both need p2 >= 1), so the
    expected set is {t2, t3, t4}, listed in declared order.
    """
    net = smoke_net()
    assert net.active((1, 1, 1, 2, 0, 1)) == ["t2", "t3", "t4"]


@settings(max_examples=100)
@given(case=net_with_marking())
def test_fire_incidence_balance(case: tuple[PetriNet, Marking]) -> None:
    """fire(m, t) - m equals the incidence row computed independently."""
    net, m = case
    place_index = {place: index for index, place in enumerate(net.places)}
    for i, t in enumerate(net.transitions):
        expected = [0] * len(net.places)
        for place, weight in net.inputs[i]:
            expected[place_index[place]] -= weight
        for place, weight in net.outputs[i]:
            expected[place_index[place]] += weight
        if net.enabled(m, t):
            fired = net.fire(m, t)
            assert [fired[j] - m[j] for j in range(len(fired))] == expected
        else:
            with pytest.raises(TransitionNotEnabledError):
                net.fire(m, t)


@settings(max_examples=100)
@given(case=net_with_marking())
def test_enabled_iff_precondition(case: tuple[PetriNet, Marking]) -> None:
    """enabled() agrees with a direct re-check of the input-arc preconditions."""
    net, m = case
    place_index = {place: index for index, place in enumerate(net.places)}
    for i, t in enumerate(net.transitions):
        expected = all(m[place_index[place]] >= weight for place, weight in net.inputs[i])
        assert net.enabled(m, t) is expected


@settings(max_examples=100)
@given(case=net_with_marking())
def test_active_consistency(case: tuple[PetriNet, Marking]) -> None:
    """active() lists exactly the enabled transitions, in declared order."""
    net, m = case
    place_index = {place: index for index, place in enumerate(net.places)}
    expected = [
        t
        for i, t in enumerate(net.transitions)
        if all(m[place_index[place]] >= weight for place, weight in net.inputs[i])
    ]
    assert net.active(m) == expected


@settings(max_examples=100)
@given(case=net_with_marking())
def test_fire_no_mutation(case: tuple[PetriNet, Marking]) -> None:
    """fire() returns a new tuple; the marking and the frozen net are untouched."""
    net, m = case
    before = (net.places, net.transitions, net.inputs, net.outputs, net.initial_marking)
    for t in net.transitions:
        if net.enabled(m, t):
            fired = net.fire(m, t)
            assert isinstance(fired, tuple)
            assert fired is not m
            assert m == case[1]
    after = (net.places, net.transitions, net.inputs, net.outputs, net.initial_marking)
    assert after == before
    assert isinstance(hash(net), int)
