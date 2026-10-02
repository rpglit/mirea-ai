"""Immutable Petri net model and firing semantics (ADR-0001).

The net is a frozen dataclass: ``places`` is the index basis for every
marking, so ``marking[i]`` is the token count on ``places[i]``. ``inputs``
and ``outputs`` are indexed by transition position, aligned with
``transitions``. The model carries no caches and is never mutated, so it can
be shared across the graph, properties and state handlers.

Smoke net (p1..p6, t1..t5, mu0 = (7, 4, 2, 5, 4, 3)):

    net.active(mu0) == ["t1", "t2", "t3", "t4", "t5"]
    net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)
"""

from __future__ import annotations

from dataclasses import dataclass

from petrinet.errors import TransitionNotEnabledError

Marking = tuple[int, ...]  # m[i] = tokens on places[i]; len(m) == len(net.places)


@dataclass(frozen=True)
class PetriNet:
    """A Petri net with arc-weighted inputs/outputs and an initial marking.

    ``places`` is declared order = index order; ``transitions`` is declared
    order; ``inputs[i]`` and ``outputs[i]`` are the ``(place, weight)`` pairs
    of ``transitions[i]``, aligned by index; ``initial_marking`` is aligned
    with ``places``.

    Smoke net (p1..p6, t1..t5, mu0 = (7, 4, 2, 5, 4, 3)):

        net.active(mu0) == ["t1", "t2", "t3", "t4", "t5"]
        net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)
    """

    places: tuple[str, ...]
    transitions: tuple[str, ...]
    inputs: tuple[tuple[tuple[str, int], ...], ...]
    outputs: tuple[tuple[tuple[str, int], ...], ...]
    initial_marking: Marking

    def _transition_index(self, t: str) -> int:
        """Return the declared position of transition ``t`` (deterministic)."""
        index = dict(zip(self.transitions, range(len(self.transitions)), strict=True))
        return index[t]

    def enabled(self, marking: Marking, t: str) -> bool:
        """Return True iff ``marking[p] >= w`` for every ``(p, w)`` in inputs of ``t``.

        Runs in O(|P|) with a single pass over the transition's input arcs.
        A transition with no input arcs is enabled at every marking.

        Smoke net: every ``t1..t5`` is enabled at mu0.
        """
        place_index = dict(zip(self.places, range(len(self.places)), strict=True))
        return all(marking[place_index[p]] >= w for p, w in self.inputs[self._transition_index(t)])

    def fire(self, marking: Marking, t: str) -> Marking:
        """Return ``marking - I(t) + O(t)`` as a new tuple.

        Rebuilds a full |P|-tuple in one pass and never mutates ``marking``
        or the net. Raises ``TransitionNotEnabledError`` if ``t`` is not
        enabled at ``marking``.

        Smoke net: ``net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)``.
        """
        if not self.enabled(marking, t):
            raise TransitionNotEnabledError(marking, t)
        place_index = dict(zip(self.places, range(len(self.places)), strict=True))
        result = list(marking)
        for p, w in self.inputs[self._transition_index(t)]:
            result[place_index[p]] -= w
        for p, w in self.outputs[self._transition_index(t)]:
            result[place_index[p]] += w
        return tuple(result)

    def active(self, marking: Marking) -> list[str]:
        """Return transitions enabled at ``marking``, in declared transition order.

        Smoke net: ``net.active(mu0) == ["t1", "t2", "t3", "t4", "t5"]``.
        """
        return [t for t in self.transitions if self.enabled(marking, t)]
