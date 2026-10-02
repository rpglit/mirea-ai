"""Parser tests for the raw text channel (FR-001; REQUIREMENTS 5.1 fixtures)."""

from __future__ import annotations

import pytest
from conftest import SMOKE_TEXT, smoke_net
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from petrinet.core import PetriNet
from petrinet.errors import ParseError
from petrinet.parser import parse_text

HEADER_LINE = "S = (P, T, I, O, µ),\n"

PARSE_ERROR_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "empty",
        "",
        "empty description",
    ),
    (
        "missing_pt_line",
        "I(t) = {p}, O(t) = {p},\nµ = (1,).\n",
        "P = {...}, T = {...}",
    ),
    (
        "bad_pt_line",
        "P = [p1], T = {t1},\nI(t1) = {p1}, O(t1) = {p1},\nµ = (1,).\n",
        "expected",
    ),
    (
        "duplicate_place",
        "P = {p1, p1}, T = {t1},\nI(t1) = {p1}, O(t1) = {p1},\nµ = (1,).\n",
        "duplicate place name",
    ),
    (
        "unknown_place_in_io",
        "P = {p1}, T = {t1},\nI(t1) = {p2}, O(t1) = {p1},\nµ = (1,).\n",
        "unknown place",
    ),
    (
        "unknown_transition",
        "P = {p1}, T = {t1},\nI(t2) = {p1}, O(t2) = {p1},\nµ = (1,).\n",
        "unknown transition",
    ),
    (
        "duplicate_io_line",
        "P = {p1}, T = {t1},\nI(t1) = {p1}, O(t1) = {p1},\n"
        "I(t1) = {p1}, O(t1) = {p1},\nµ = (1,).\n",
        "duplicate I/O line",
    ),
    (
        "missing_io_line",
        "P = {p1, p2}, T = {t1, t2},\nI(t1) = {p1}, O(t1) = {p1},\nµ = (1, 0).\n",
        "missing I/O line",
    ),
    (
        "marking_length",
        "P = {p1, p2}, T = {t1},\nI(t1) = {p1}, O(t1) = {p1},\nµ = (1,).\n",
        "expected 2",
    ),
    (
        "non_integer_marking",
        "P = {p1}, T = {t1},\nI(t1) = {p1}, O(t1) = {p1},\nµ = (x,).\n",
        "non-integer marking value",
    ),
    (
        "garbage_line",
        "P = {p1}, T = {t1},\nhello world\nI(t1) = {p1}, O(t1) = {p1},\nµ = (1,).\n",
        "expected",
    ),
    (
        "bad_name",
        "P = {1p}, T = {t1},\nI(t1) = {1p}, O(t1) = {1p},\nµ = (1,).\n",
        "invalid place name",
    ),
)


def _expand_arcs(arcs: tuple[tuple[str, int], ...]) -> str:
    """Expand (place, weight) arcs into repeated place names for the text form."""
    names: list[str] = []
    for place, weight in arcs:
        names.extend([place] * weight)
    return ", ".join(names)


def render_text(net: PetriNet) -> str:
    """Render a net to the parser's canonical text notation (no header line)."""
    lines = [f"P = {{{', '.join(net.places)}}}, T = {{{', '.join(net.transitions)}}},"]
    for t, ins, outs in zip(net.transitions, net.inputs, net.outputs, strict=True):
        lines.append(f"I({t}) = {{{_expand_arcs(ins)}}}, O({t}) = {{{_expand_arcs(outs)}}}," )
    lines.append(f"µ = ({', '.join(str(v) for v in net.initial_marking)}).")
    return "\n".join(lines)


@st.composite
def net_strategy(draw: DrawFn) -> tuple[PetriNet, str]:
    """Draw a small random net (p0..p3, t0..t3) and its canonical text rendering."""
    n_places = draw(st.integers(min_value=1, max_value=4))
    n_transitions = draw(st.integers(min_value=1, max_value=4))
    places = tuple(f"p{i}" for i in range(n_places))
    transitions = tuple(f"t{i}" for i in range(n_transitions))

    def arcs() -> tuple[tuple[str, int], ...]:
        drawn = draw(
            st.lists(
                st.tuples(
                    st.integers(min_value=0, max_value=n_places - 1),
                    st.integers(min_value=1, max_value=3),
                ),
                min_size=0,
                max_size=n_places,
                unique_by=lambda arc: arc[0],
            )
        )
        return tuple((places[index], weight) for index, weight in sorted(drawn))

    values = st.integers(min_value=0, max_value=4)
    marking = tuple(draw(st.lists(values, min_size=n_places, max_size=n_places)))
    net = PetriNet(
        places=places,
        transitions=transitions,
        inputs=tuple(arcs() for _ in range(n_transitions)),
        outputs=tuple(arcs() for _ in range(n_transitions)),
        initial_marking=marking,
    )
    return net, render_text(net)


def test_smoke_text_parses_to_model() -> None:
    """The REQUIREMENTS 5.1 smoke text parses to the fixture net."""
    assert parse_text(SMOKE_TEXT) == smoke_net()


def test_mu_spelling_variants() -> None:
    """The marking line also accepts the 'mu' spelling and the Greek letter μ."""
    assert parse_text(SMOKE_TEXT.replace("µ = ", "mu = ")) == smoke_net()
    assert parse_text(SMOKE_TEXT.replace("µ", "μ")) == smoke_net()


def test_header_optional() -> None:
    """Dropping the 'S = (...)' header line still parses to the same net."""
    assert parse_text(SMOKE_TEXT.removeprefix(HEADER_LINE)) == smoke_net()


def test_empty_io_sets() -> None:
    """Empty I/O braces parse; a transition without inputs is always enabled."""
    net = parse_text("P = {a}, T = {t},\nI(t) = {}, O(t) = {a},\nµ = (0,).\n")
    assert net.inputs[0] == ()
    assert net.enabled((0,), "t") is True


def test_repetition_is_weight() -> None:
    """A place repeated k times in an I/O set becomes an arc of weight k."""
    net = parse_text("P = {p}, T = {t},\nI(t) = {p, p, p}, O(t) = {p},\nµ = (0,).\n")
    assert net.inputs[0] == (("p", 3),)


@pytest.mark.parametrize(
    ("name", "text", "substring"), PARSE_ERROR_CASES, ids=[case[0] for case in PARSE_ERROR_CASES]
)
def test_parse_error_cases(name: str, text: str, substring: str) -> None:
    """Each malformed description raises ParseError with the expected message."""
    with pytest.raises(ParseError) as excinfo:
        parse_text(text)
    err = excinfo.value
    assert substring in str(err)
    assert err.position >= 0


def test_position_accuracy() -> None:
    """The ParseError position is the absolute offset of the offending token."""
    text = "P = {p1}, T = {t1},\nI(t1) = {p1}, O(t1) = {p1},\nµ = (1, x).\n"
    with pytest.raises(ParseError) as excinfo:
        parse_text(text)
    assert excinfo.value.position == text.index("x")


def test_marking_must_be_last() -> None:
    """An I/O line after the marking line is rejected as a parse error."""
    text = "P = {p1}, T = {t1},\nµ = (1,).\nI(t1) = {p1}, O(t1) = {p1},\n"
    with pytest.raises(ParseError):
        parse_text(text)


@settings(max_examples=100)
@given(case=net_strategy())
def test_text_round_trip(case: tuple[PetriNet, str]) -> None:
    """A random net rendered to text parses back to an equal net."""
    net, rendered = case
    assert parse_text(rendered) == net
