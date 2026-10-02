"""Parser tests for the JSON (FR-002) and form (FR-003) intake channels."""

from __future__ import annotations

import json
from typing import cast

import pytest
from conftest import SMOKE_JSON, SMOKE_TEXT, smoke_net

from petrinet.errors import ValidationError
from petrinet.parser import parse_form, parse_json, parse_text

SMOKE_ARCS: list[dict[str, object]] = [
    {"source": "p1", "target": "t1", "weight": 2, "direction": "input"},
    {"source": "p1", "target": "t2", "weight": 1, "direction": "input"},
    {"source": "p6", "target": "t2", "weight": 1, "direction": "input"},
    {"source": "p2", "target": "t3", "weight": 1, "direction": "input"},
    {"source": "p2", "target": "t4", "weight": 1, "direction": "input"},
    {"source": "p3", "target": "t4", "weight": 1, "direction": "input"},
    {"source": "p4", "target": "t4", "weight": 2, "direction": "input"},
    {"source": "p5", "target": "t5", "weight": 2, "direction": "input"},
    {"source": "t1", "target": "p2", "weight": 1, "direction": "output"},
    {"source": "t2", "target": "p3", "weight": 2, "direction": "output"},
    {"source": "t3", "target": "p4", "weight": 3, "direction": "output"},
    {"source": "t4", "target": "p5", "weight": 1, "direction": "output"},
    {"source": "t4", "target": "p6", "weight": 1, "direction": "output"},
    {"source": "t5", "target": "p1", "weight": 1, "direction": "output"},
    {"source": "t5", "target": "p3", "weight": 1, "direction": "output"},
]

SMOKE_FORM: dict[str, object] = {
    "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
    "transitions": ["t1", "t2", "t3", "t4", "t5"],
    "arcs": SMOKE_ARCS,
    "initial_marking": {"p1": 7, "p2": 4, "p3": 2, "p4": 5, "p5": 4, "p6": 3},
}


def _copy_json(payload: dict[str, object]) -> dict[str, object]:
    """Deep-copy a JSON-safe payload through a serialization round-trip."""
    raw = json.loads(json.dumps(payload))
    return cast(dict[str, object], raw)


def _problems(error: ValidationError) -> list[dict[str, str]]:
    """Return the problem entries carried by a ValidationError."""
    return error.problems


def _with_input_entry(t: str, entry: dict[str, object]) -> dict[str, object]:
    """SMOKE_JSON with inputs[t] set to entry."""
    payload = _copy_json(SMOKE_JSON)
    inputs = cast(dict[str, object], payload["inputs"])
    payload["inputs"] = {**inputs, t: entry}
    return payload


def _without_marking_place(place: str) -> dict[str, object]:
    """SMOKE_JSON with initial_marking[place] removed."""
    payload = _copy_json(SMOKE_JSON)
    marking = cast(dict[str, object], payload["initial_marking"])
    payload["initial_marking"] = {k: v for k, v in marking.items() if k != place}
    return payload


def _with_extra_marking_key() -> dict[str, object]:
    """SMOKE_JSON with initial_marking.pX = 0 added."""
    payload = _copy_json(SMOKE_JSON)
    marking = cast(dict[str, object], payload["initial_marking"])
    payload["initial_marking"] = {**marking, "pX": 0}
    return payload


def _invalid_cases() -> list[tuple[str, dict[str, object], str | None, str | None]]:
    """SMOKE_JSON mutations as (name, payload, path fragment, message fragment)."""
    cases: list[tuple[str, dict[str, object], str | None, str | None]] = []

    dup_places = _copy_json(SMOKE_JSON)
    dup_places["places"] = ["p1", "p1", "p2", "p3", "p4", "p5", "p6"]
    cases.append(("duplicate place name", dup_places, "places", None))

    no_transitions = _copy_json(SMOKE_JSON)
    no_transitions["transitions"] = []
    cases.append(("empty transitions", no_transitions, "transitions", None))

    cases.append(("zero weight", _with_input_entry("t1", {"p1": 0}), "inputs.t1.p1", None))
    cases.append(("negative weight", _with_input_entry("t1", {"p1": -1}), "inputs.t1.p1", None))
    non_int = _with_input_entry("t1", {"p1": 2.5})
    cases.append(("non-integer weight", non_int, "inputs.t1.p1", None))
    unknown_place = _with_input_entry("t1", {"pX": 1})
    cases.append(("unknown place in arc", unknown_place, None, "unknown place"))
    unknown_t = _with_input_entry("tX", {"p1": 1})
    cases.append(("unknown transition", unknown_t, None, "unknown transition"))
    missing = _without_marking_place("p4")
    cases.append(("missing marking entry", missing, None, "missing entry for place"))
    extra_marking = _with_extra_marking_key()
    cases.append(("extra marking key", extra_marking, None, "unknown place"))

    bad_name = _copy_json(SMOKE_JSON)
    bad_name["places"] = ["1p"]
    cases.append(("bad place name", bad_name, "places", None))

    not_list = _copy_json(SMOKE_JSON)
    not_list["places"] = "p1"
    cases.append(("places not a list", not_list, "places", None))

    extra_key = _copy_json(SMOKE_JSON)
    extra_key["x"] = 1
    cases.append(("extra top-level key", extra_key, None, "'x'"))
    return cases


def test_json_smoke_equals_model() -> None:
    """parse_json(SMOKE_JSON) reproduces the hand-built smoke net exactly."""
    net = parse_json(SMOKE_JSON)
    assert net == smoke_net()
    assert net.places == ("p1", "p2", "p3", "p4", "p5", "p6")
    assert net.transitions == ("t1", "t2", "t3", "t4", "t5")
    assert net.initial_marking == (7, 4, 2, 5, 4, 3)
    assert net.inputs[0] == (("p1", 2),)
    assert net.inputs[3] == (("p2", 1), ("p3", 1), ("p4", 2))
    assert net.outputs[2] == (("p4", 3),)


def test_json_key_order_determinism() -> None:
    """Reversed key order in inputs.t4 and initial_marking parses identically."""
    payload = _copy_json(SMOKE_JSON)
    inputs = cast(dict[str, object], payload["inputs"])
    payload["inputs"] = {**inputs, "t4": {"p4": 2, "p3": 1, "p2": 1}}
    marking = cast(dict[str, object], payload["initial_marking"])
    payload["initial_marking"] = {key: marking[key] for key in reversed(list(marking))}
    assert parse_json(payload) == smoke_net()


def test_json_absent_inputs_outputs() -> None:
    """Absent inputs/outputs keys normalize to empty arc maps; t1 is enabled."""
    payload: dict[str, object] = {
        "places": ["p1"],
        "transitions": ["t1"],
        "initial_marking": {"p1": 0},
    }
    net = parse_json(payload)
    assert net.inputs[0] == ()
    assert net.outputs[0] == ()
    assert net.enabled((0,), "t1") is True
    assert net.enabled((3,), "t1") is True


def test_form_smoke_equals_model() -> None:
    """The 15-arc form payload of the smoke net parses to the same model."""
    assert parse_form(SMOKE_FORM) == smoke_net()


def test_form_duplicate_arc() -> None:
    """Appending a copy of the first arc is rejected at arcs.15."""
    payload: dict[str, object] = {**SMOKE_FORM, "arcs": [*SMOKE_ARCS, SMOKE_ARCS[0]]}
    with pytest.raises(ValidationError) as exc_info:
        parse_form(payload)
    problems = _problems(exc_info.value)
    assert any(p["path"] == "arcs.15" and "duplicate arc" in p["message"] for p in problems)


def test_form_bad_direction() -> None:
    """An arc with direction 'both' is rejected at arcs.0.direction."""
    bad: dict[str, object] = {"source": "p1", "target": "t1", "weight": 2, "direction": "both"}
    payload: dict[str, object] = {**SMOKE_FORM, "arcs": [bad, *SMOKE_ARCS[1:]]}
    with pytest.raises(ValidationError) as exc_info:
        parse_form(payload)
    problems = _problems(exc_info.value)
    assert any(p["path"] == "arcs.0.direction" for p in problems)


def test_form_zero_weight() -> None:
    """An arc with weight 0 is rejected at arcs.0.weight."""
    bad: dict[str, object] = {"source": "p1", "target": "t1", "weight": 0, "direction": "input"}
    payload: dict[str, object] = {**SMOKE_FORM, "arcs": [bad, *SMOKE_ARCS[1:]]}
    with pytest.raises(ValidationError) as exc_info:
        parse_form(payload)
    problems = _problems(exc_info.value)
    assert any(p["path"] == "arcs.0.weight" for p in problems)


def test_form_missing_arcs() -> None:
    """A form payload without the 'arcs' key is rejected at path 'arcs'."""
    payload = {key: value for key, value in SMOKE_FORM.items() if key != "arcs"}
    with pytest.raises(ValidationError) as exc_info:
        parse_form(payload)
    problems = _problems(exc_info.value)
    assert any(p["path"] == "arcs" for p in problems)


def test_json_invalid_cases() -> None:
    """Every SMOKE_JSON mutation raises ValidationError with the expected problem."""
    for name, payload, path_frag, msg_frag in _invalid_cases():
        with pytest.raises(ValidationError) as exc_info:
            parse_json(payload)
        problems = _problems(exc_info.value)
        if path_frag is not None:
            assert any(path_frag in problem["path"] for problem in problems), name
        if msg_frag is not None:
            assert any(msg_frag in problem["message"] for problem in problems), name


def test_text_channel_equals_model() -> None:
    """parse_text(SMOKE_TEXT) reaches the same model (cross-channel check)."""
    assert parse_text(SMOKE_TEXT) == smoke_net()


def test_missing_marking_place_message() -> None:
    """Deleting initial_marking['p6'] yields exactly the p6 missing-entry problem."""
    payload = _without_marking_place("p6")
    with pytest.raises(ValidationError) as exc_info:
        parse_json(payload)
    problems = _problems(exc_info.value)
    assert len(problems) == 1
    assert problems[0]["path"] == "initial_marking"
    assert problems[0]["message"] == "missing entry for place 'p6'"
