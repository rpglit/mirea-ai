"""Parser tests for the v2 model extensions (inhibitors, priorities, delays, colors).

Covers the JSON channel (parse_json), the form channel (parse_form) and the
pass-2 cross-field rules of the shared validator. The raw text channel is
classical-only on purpose (grammar of the methodic) and is NOT exercised here
(see test_parser_text.py).
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from conftest import SMOKE_JSON, smoke_net
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from petrinet.core import Colors, PetriNet
from petrinet.errors import ValidationError
from petrinet.parser import parse_form, parse_json


def _copy_json(payload: dict[str, object]) -> dict[str, object]:
    """Deep-copy a JSON-safe payload through a serialization round-trip."""
    raw = json.loads(json.dumps(payload))
    return cast(dict[str, object], raw)


def _problems(error: ValidationError) -> list[dict[str, str]]:
    """Return the problem entries carried by a ValidationError."""
    return error.problems


def _with(field: str, value: object) -> dict[str, object]:
    """SMOKE_JSON with the top-level ``field`` set to ``value``."""
    payload = _copy_json(SMOKE_JSON)
    payload[field] = value
    return payload


# ---------------------------------------------------------------------------
# A full v2 net exercising all four extension fields.
# ---------------------------------------------------------------------------

V2_JSON: dict[str, object] = {
    "places": ["p1", "p2", "p3", "p4"],
    "transitions": ["t1", "t2", "t3"],
    "inputs": {"t1": {"p1": 1}, "t2": {"p1": 1}, "t3": {"p2": 1}},
    "outputs": {"t1": {"p2": 1}, "t2": {"p3": 1}, "t3": {"p4": 1}},
    "initial_marking": {"p1": 2, "p2": 0, "p3": 0, "p4": 0},
    "inhibitors": {"t1": ["p3"], "t3": ["p2", "p1"]},
    "priorities": {"t1": 1, "t2": 0, "t3": 2},
    "delays": {"t1": {"p2": 3}, "t3": {"p4": 1}},
    "colors": {
        "initial_values": {"p1": ["red", "blue"]},
        "guards": {"t2": ["x > 0"], "t3": ["y >= 1"]},
        "output_exprs": {"t1": ["v + 1"]},
    },
}


def v2_expected_net() -> PetriNet:
    """The hand-built PetriNet that V2_JSON must parse to (deterministic order)."""
    return PetriNet(
        places=("p1", "p2", "p3", "p4"),
        transitions=("t1", "t2", "t3"),
        inputs=((("p1", 1),), (("p1", 1),), (("p2", 1),)),
        outputs=((("p2", 1),), (("p3", 1),), (("p4", 1),)),
        initial_marking=(2, 0, 0, 0),
        inhibitors=(("p3",), (), ("p1", "p2")),
        priorities=(1, 0, 2),
        delays=((("p2", 3),), (), (("p4", 1),)),
        colors=Colors(
            initial_values={"p1": ["red", "blue"]},
            guards={"t2": ["x > 0"], "t3": ["y >= 1"]},
            output_exprs={"t1": ["v + 1"]},
        ),
    )


def test_json_v2_full_net() -> None:
    """All four v2 fields parse to the aligned, place-sorted core tuples."""
    net = parse_json(V2_JSON)
    assert net == v2_expected_net()
    assert net.inhibitors == (("p3",), (), ("p1", "p2"))
    assert net.priorities == (1, 0, 2)
    assert net.delays == ((("p2", 3),), (), (("p4", 1),))
    assert net.colors is not None
    assert net.colors.initial_values == {"p1": ["red", "blue"]}
    assert net.colors.guards == {"t2": ["x > 0"], "t3": ["y >= 1"]}
    assert net.colors.output_exprs == {"t1": ["v + 1"]}


def test_json_v2_key_order_determinism() -> None:
    """Shuffled key order inside the v2 maps parses to the same net."""
    payload = _copy_json(V2_JSON)
    payload["inhibitors"] = {"t3": ["p2", "p1"], "t1": ["p3"]}
    payload["priorities"] = {"t3": 2, "t1": 1, "t2": 0}
    payload["delays"] = {"t3": {"p4": 1}, "t1": {"p2": 3}}
    assert parse_json(payload) == v2_expected_net()


def test_json_classical_fields_absent() -> None:
    """Without v2 keys the net stays classical (all extension fields None)."""
    net = parse_json(SMOKE_JSON)
    assert net == smoke_net()
    assert net.inhibitors is None
    assert net.priorities is None
    assert net.delays is None
    assert net.colors is None


# ---------------------------------------------------------------------------
# pass-2 cross-field validation of the v2 fields.
# ---------------------------------------------------------------------------


def test_json_inhibitors_unknown_transition() -> None:
    """inhibitors keyed by an undeclared transition is rejected."""
    payload = _with("inhibitors", {"tX": ["p1"]})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "inhibitors.tX" and p["message"] == "unknown transition" for p in problems
    )


def test_json_inhibitors_unknown_place() -> None:
    """an inhibitor place not declared in P is rejected."""
    payload = _with("inhibitors", {"t1": ["pX"]})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "inhibitors.t1.pX" and p["message"] == "unknown place" for p in problems
    )


def test_json_inhibitors_duplicate_place() -> None:
    """the same place twice in one inhibitor list fails pass 1 (uniqueItems)."""
    payload = _with("inhibitors", {"t1": ["p2", "p2"]})
    with pytest.raises(ValidationError):
        parse_json(payload)


def test_json_priorities_unknown_transition() -> None:
    """priorities keyed by an undeclared transition is rejected."""
    payload = _with("priorities", {"tX": 1})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "priorities.tX" and p["message"] == "unknown transition" for p in problems
    )


def test_json_priorities_negative() -> None:
    """a negative priority fails pass 1 (minimum 0) at priorities.t1."""
    payload = _with("priorities", {"t1": -1})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any("priorities.t1" in p["path"] for p in problems)


def test_json_priorities_missing_transition_defaults_zero() -> None:
    """a declared transition absent from priorities gets priority 0."""
    payload = _with("priorities", {"t1": 2})
    net = parse_json(payload)
    assert net.priorities == (2, 0, 0, 0, 0)


def test_json_delays_unknown_transition() -> None:
    """delays keyed by an undeclared transition is rejected."""
    payload = _with("delays", {"tX": {"p2": 1}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "delays.tX" and p["message"] == "unknown transition" for p in problems
    )


def test_json_delays_non_output_arc() -> None:
    """a delay on a pair without an output arc is rejected at delays.t1.p3."""
    payload = _with("delays", {"t1": {"p3": 2}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "delays.t1.p3" and "no output arc" in p["message"] for p in problems
    )


def test_json_delays_input_only_arc() -> None:
    """a delay on an INPUT-only arc (p1 is in I(t2), not O(t2)) is rejected."""
    payload = _with("delays", {"t2": {"p1": 2}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "delays.t2.p1" and "no output arc" in p["message"] for p in problems
    )


def test_json_delays_zero_tau() -> None:
    """tau = 0 fails pass 1 (minimum 1) at delays.t1.p2."""
    payload = _with("delays", {"t1": {"p2": 0}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any("delays.t1.p2" in p["path"] for p in problems)


def test_json_colors_unknown_place() -> None:
    """colors.initial_values keyed by an undeclared place is rejected."""
    payload = _with("colors", {"initial_values": {"pX": ["red"]}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "colors.initial_values.pX"
        and p["message"] == "unknown place"
        for p in problems
    )


def test_json_colors_unknown_transition() -> None:
    """colors.guards keyed by an undeclared transition is rejected."""
    payload = _with("colors", {"guards": {"tX": ["x > 0"]}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any(
        p["path"] == "colors.guards.tX"
        and p["message"] == "unknown transition"
        for p in problems
    )


def test_json_colors_empty_guard_string() -> None:
    """an empty guard expression fails pass 1 (minLength 1)."""
    payload = _with("colors", {"guards": {"t1": [""]}})
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert any("colors.guards.t1" in p["path"] for p in problems)


# ---------------------------------------------------------------------------
# Form channel (FR-003) with the v2 extensions.
# ---------------------------------------------------------------------------

FORM_V2_ARCS: list[dict[str, object]] = [
    {"source": "p1", "target": "t1", "weight": 1, "direction": "input"},
    {"source": "p1", "target": "t2", "weight": 1, "direction": "input"},
    {"source": "t1", "target": "p2", "weight": 1, "direction": "output"},
    {"source": "t2", "target": "p3", "weight": 1, "direction": "output"},
    # inhibitor arcs; the first omits the weight (allowed, fixed to 1).
    # p2->t1 coexists with the output arc t1->p2 (same names, different kind).
    {"source": "p2", "target": "t1", "direction": "inhibitor"},
    {"source": "p3", "target": "t2", "weight": 1, "direction": "inhibitor"},
]

FORM_V2: dict[str, object] = {
    "places": ["p1", "p2", "p3"],
    "transitions": ["t1", "t2"],
    "arcs": FORM_V2_ARCS,
    "priorities": {"t1": 1, "t2": 0},
    "delays": {"t1": {"p2": 2}},
    "initial_marking": {"p1": 1, "p2": 0, "p3": 0},
}


def test_form_v2_net() -> None:
    """Inhibitor arcs plus priorities and delays parse to the v2 model."""
    net = parse_form(FORM_V2)
    assert net.places == ("p1", "p2", "p3")
    assert net.transitions == ("t1", "t2")
    assert net.inputs == ((("p1", 1),), (("p1", 1),))
    assert net.outputs == ((("p2", 1),), (("p3", 1),))
    assert net.initial_marking == (1, 0, 0)
    assert net.inhibitors == (("p2",), ("p3",))
    assert net.priorities == (1, 0)
    assert net.delays == ((("p2", 2),), ())
    assert net.colors is None


def test_form_inhibitor_duplicate_rejected() -> None:
    """The same inhibitor arc twice is a duplicate-arc error at arcs.6."""
    payload: dict[str, object] = {
        **FORM_V2,
        "arcs": [*FORM_V2_ARCS, {"source": "p2", "target": "t1", "direction": "inhibitor"}],
    }
    with pytest.raises(ValidationError) as exc_info:
        parse_form(payload)
    problems = _problems(exc_info.value)
    assert any(p["path"] == "arcs.6" and "duplicate arc" in p["message"] for p in problems)


def test_form_inhibitor_bad_weight() -> None:
    """An inhibitor arc with weight 2 is rejected at arcs.0.weight."""
    bad: dict[str, object] = {
        "source": "p1",
        "target": "t1",
        "weight": 2,
        "direction": "inhibitor",
    }
    payload: dict[str, object] = {**FORM_V2, "arcs": [bad, *FORM_V2_ARCS[1:]]}
    with pytest.raises(ValidationError) as exc_info:
        parse_form(payload)
    problems = _problems(exc_info.value)
    assert any(p["path"] == "arcs.0.weight" and "inhibitor" in p["message"] for p in problems)


def test_form_classical_stays_classical() -> None:
    """A form payload without v2 fields yields None extension fields."""
    payload: dict[str, object] = {
        "places": ["p1"],
        "transitions": ["t1"],
        "arcs": [
            {"source": "p1", "target": "t1", "weight": 1, "direction": "input"},
            {"source": "t1", "target": "p1", "weight": 1, "direction": "output"},
        ],
        "initial_marking": {"p1": 0},
    }
    net = parse_form(payload)
    assert net.inhibitors is None
    assert net.priorities is None
    assert net.delays is None
    assert net.colors is None


# ---------------------------------------------------------------------------
# Hypothesis: random v2 payloads round-trip through parse_json.
# ---------------------------------------------------------------------------


@st.composite
def v2_payload_strategy(draw: DrawFn) -> dict[str, object]:
    """Draw a small random net as a canonical JSON payload, with optional v2 fields."""
    n_places = draw(st.integers(min_value=1, max_value=4))
    n_transitions = draw(st.integers(min_value=1, max_value=3))
    places = [f"p{i}" for i in range(n_places)]
    transitions = [f"t{i}" for i in range(n_transitions)]

    def arc_map() -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for t in transitions:
            drawn = draw(
                st.lists(
                    st.tuples(
                        st.integers(min_value=0, max_value=n_places - 1),
                        st.integers(min_value=1, max_value=3),
                    ),
                    max_size=n_places,
                    unique_by=lambda arc: arc[0],
                )
            )
            result[t] = {places[index]: weight for index, weight in sorted(drawn)}
        return result

    inputs = arc_map()
    outputs = arc_map()
    payload: dict[str, object] = {
        "places": places,
        "transitions": transitions,
        "inputs": inputs,
        "outputs": outputs,
        "initial_marking": {p: draw(st.integers(min_value=0, max_value=4)) for p in places},
    }

    if draw(st.booleans()):
        inhibitors: dict[str, list[str]] = {}
        for t in draw(st.lists(st.sampled_from(transitions), unique=True)):
            inhibitors[t] = draw(
                st.lists(st.sampled_from(places), unique=True, max_size=n_places)
            )
        if inhibitors:
            payload["inhibitors"] = inhibitors

    if draw(st.booleans()):
        priorities: dict[str, int] = {}
        for t in draw(st.lists(st.sampled_from(transitions), unique=True)):
            priorities[t] = draw(st.integers(min_value=0, max_value=3))
        if priorities:
            payload["priorities"] = priorities

    if draw(st.booleans()):
        delays: dict[str, dict[str, int]] = {}
        for t in draw(st.lists(st.sampled_from(transitions), unique=True)):
            out_places = list(outputs[t])
            if out_places:
                chosen = draw(st.lists(st.sampled_from(out_places), unique=True))
                delays[t] = {p: draw(st.integers(min_value=1, max_value=5)) for p in chosen}
        if delays:
            payload["delays"] = delays

    return payload


@settings(max_examples=50)
@given(payload=v2_payload_strategy())
def test_hypothesis_v2_round_trip(payload: dict[str, object]) -> None:
    """A random v2 payload parses, survives a JSON round-trip, keeps its fields."""
    net = parse_json(payload)
    assert parse_json(_copy_json(payload)) == net

    places = cast(list[str], payload["places"])
    transitions = cast(list[str], payload["transitions"])
    outputs = cast(dict[str, dict[str, int]], payload["outputs"])

    if "inhibitors" in payload:
        raw = cast(dict[str, list[str]], payload["inhibitors"])
        assert net.inhibitors is not None
        assert net.inhibitors == tuple(
            tuple(sorted(raw.get(t, []), key=places.index)) for t in transitions
        )
    else:
        assert net.inhibitors is None

    if "priorities" in payload:
        raw = cast(dict[str, int], payload["priorities"])
        assert net.priorities is not None
        assert net.priorities == tuple(raw.get(t, 0) for t in transitions)
    else:
        assert net.priorities is None

    if "delays" in payload:
        raw = cast(dict[str, dict[str, int]], payload["delays"])
        assert net.delays is not None
        assert net.delays == tuple(
            tuple(
                sorted(
                    ((p, tau) for p, tau in raw.get(t, {}).items()),
                    key=lambda pt: places.index(pt[0]),
                )
            )
            for t in transitions
        )
        # every delayed pair is a real output arc
        for t, entry in raw.items():
            for p in entry:
                assert p in outputs.get(t, {})
    else:
        assert net.delays is None


@settings(max_examples=50)
@given(
    colors=st.fixed_dictionaries(
        {
            "initial_values": st.dictionaries(
                st.sampled_from(["p1", "p2"]),
                st.lists(st.text(min_size=1, max_size=3, alphabet="abc"), max_size=2),
            ),
            "guards": st.dictionaries(
                st.sampled_from(["t1"]),
                st.lists(
                    st.text(min_size=1, max_size=3, alphabet="abc>0"), min_size=1, max_size=2
                ),
            ),
            "output_exprs": st.dictionaries(
                st.sampled_from(["t1"]),
                st.lists(st.text(min_size=1, max_size=3, alphabet="abc+1"), max_size=2),
            ),
        }
    )
)
def test_hypothesis_colors_round_trip(colors: dict[str, dict[str, list[str]]]) -> None:
    """A random colored payload round-trips and preserves the Colors layer."""
    payload: dict[str, object] = {
        "places": ["p1", "p2"],
        "transitions": ["t1"],
        "initial_marking": {"p1": 0, "p2": 0},
        "colors": colors,
    }
    net = parse_json(payload)
    assert parse_json(_copy_json(payload)) == net
    assert net.colors is not None
    assert net.colors.initial_values == colors["initial_values"]
    assert net.colors.guards == colors["guards"]
    assert net.colors.output_exprs == colors["output_exprs"]
