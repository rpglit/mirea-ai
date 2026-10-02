"""Shared test base for the backend test suite.

Other test modules import the smoke-net fixture (``smoke_net`` / ``smoke``)
and the REQUIREMENTS section 5.1/5.2 fixtures (``SMOKE_TEXT`` / ``SMOKE_JSON``)
from this module instead of redefining them.
"""

from __future__ import annotations

import pytest

from petrinet.core import PetriNet

SMOKE_TEXT: str = """S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3)."""

SMOKE_JSON: dict[str, object] = {
    "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
    "transitions": ["t1", "t2", "t3", "t4", "t5"],
    "inputs": {
        "t1": {"p1": 2},
        "t2": {"p1": 1, "p6": 1},
        "t3": {"p2": 1},
        "t4": {"p2": 1, "p3": 1, "p4": 2},
        "t5": {"p5": 2},
    },
    "outputs": {
        "t1": {"p2": 1},
        "t2": {"p3": 2},
        "t3": {"p4": 3},
        "t4": {"p5": 1, "p6": 1},
        "t5": {"p1": 1, "p3": 1},
    },
    "initial_marking": {"p1": 7, "p2": 4, "p3": 2, "p4": 5, "p5": 4, "p6": 3},
}


def smoke_net() -> PetriNet:
    """The task fixture net (REQUIREMENTS 5.1), built inline."""
    return PetriNet(
        places=("p1", "p2", "p3", "p4", "p5", "p6"),
        transitions=("t1", "t2", "t3", "t4", "t5"),
        inputs=(
            (("p1", 2),),
            (("p1", 1), ("p6", 1)),
            (("p2", 1),),
            (("p2", 1), ("p3", 1), ("p4", 2)),
            (("p5", 2),),
        ),
        outputs=(
            (("p2", 1),),
            (("p3", 2),),
            (("p4", 3),),
            (("p5", 1), ("p6", 1)),
            (("p1", 1), ("p3", 1)),
        ),
        initial_marking=(7, 4, 2, 5, 4, 3),
    )


@pytest.fixture
def smoke() -> PetriNet:
    """The task fixture net (REQUIREMENTS 5.1), exposed as a pytest fixture."""
    return smoke_net()
