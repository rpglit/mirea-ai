"""Immutable Petri net model (v2) and firing semantics (ADR-0001, ADR-0009).

The net is a frozen dataclass: ``places`` is the index basis for every
marking, so ``marking[i]`` is the token count on ``places[i]``. ``inputs``
and ``outputs`` are indexed by transition position, aligned with
``transitions``. The model carries no caches and is never mutated, so it can
be shared across the graph, properties and state handlers.

v2 extends the round-1 model with optional fields (all default to ``None``
= classical net, behavior identical to round 1):

- ``inhibitors``: ⊣(t) per transition — inhibitor arcs of weight 1; a
  transition is disabled while any of its inhibitor places holds tokens;
- ``priorities``: Pr t per transition; inside a conflict group only the
  transition(s) with the maximal priority stay active (M8);
- ``delays``: τ on OUTPUT arcs t→p, τ ≥ 1; the core stores the data only,
  τ-availability (the ``usable`` token vector) is passed by solvers_pn;
- ``colors``: the colored layer (A-21) — data only, no semantics here.

Smoke net (p1..p6, t1..t5, mu0 = (7, 4, 2, 5, 4, 3)):

    net.active(mu0) == ["t1", "t2", "t3", "t4", "t5"]
    net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from petrinet.errors import ConflictError, TransitionNotEnabledError

ArcWeight = tuple[str, int]  # (place, weight)
Marking = tuple[int, ...]  # m[i] = tokens on places[i]; len(m) == len(net.places)


@dataclass(frozen=True)
class Colors:
    """Colored layer (A-21): data only, no semantics.

    ``initial_values`` maps a place to the values of its initial tokens;
    ``guards`` maps a transition to the guard expressions of its input arcs
    (one per input arc); ``output_exprs`` maps a transition to the value
    expressions of the tokens placed on its output arcs. Evaluating guards
    and expressions lives in solvers_pn (safe parser, A-21).
    """

    initial_values: dict[str, list[str]]
    guards: dict[str, list[str]]
    output_exprs: dict[str, list[str]]


@dataclass(frozen=True)
class PetriNet:
    """A Petri net (v2) with arc-weighted inputs/outputs and an initial marking.

    ``places`` is declared order = index order; ``transitions`` is declared
    order; ``inputs[i]`` and ``outputs[i]`` are the ``(place, weight)`` pairs
    of ``transitions[i]``, aligned by index; ``initial_marking`` is aligned
    with ``places``.

    v2 optional fields (all default ``None``; ``inhibitors``/``priorities``/
    ``delays`` are aligned with ``transitions``):

    - ``inhibitors[i]``: ⊣(t_i) — the places of the weight-1 inhibitor arcs;
    - ``priorities[i]``: Pr t_i; ``None`` — no priorities;
    - ``delays[i]``: τ on the output arcs t_i→p (τ ≥ 1), data only;
    - ``colors``: the colored layer (A-21), data only.

    With ``inhibitors = priorities = delays = colors = None`` the behavior is
    identical to round 1 (anchors D-009…D-014, D-035).

    Smoke net (p1..p6, t1..t5, mu0 = (7, 4, 2, 5, 4, 3)):

        net.active(mu0) == ["t1", "t2", "t3", "t4", "t5"]
        net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)
    """

    places: tuple[str, ...]
    transitions: tuple[str, ...]
    inputs: tuple[tuple[ArcWeight, ...], ...]
    outputs: tuple[tuple[ArcWeight, ...], ...]
    initial_marking: Marking
    inhibitors: tuple[tuple[str, ...], ...] | None = None
    priorities: tuple[int, ...] | None = None
    delays: tuple[tuple[tuple[str, int], ...], ...] | None = None
    colors: Colors | None = None

    def _place_index(self) -> dict[str, int]:
        """Return the mapping place name -> declared index (deterministic)."""
        return dict(zip(self.places, range(len(self.places)), strict=True))

    def _transition_index(self, t: str) -> int:
        """Return the declared position of transition ``t`` (deterministic)."""
        index = dict(zip(self.transitions, range(len(self.transitions)), strict=True))
        return index[t]

    def enabled(self, marking: Marking, t: str, *, usable: Marking | None = None) -> bool:
        """Return True iff ``t`` is enabled at ``marking`` (M2, with ⊣ — M2⊣).

        ``marking[p] >= w`` for every ``(p, w)`` in I(t) **and**, for every
        inhibitor place ``p`` in ⊣(t), ``usable[p] == 0`` (a weight-1
        inhibitor arc blocks while the place holds at least one token).
        ``usable`` is the vector of tokens available right now (timed nets);
        it defaults to ``marking``, so the classical call is unchanged.
        A transition with no input arcs and no inhibitor arcs is enabled at
        every marking.

        Example: net with I(t) = {p1: 1}, ⊣(t) = {p2}:
        ``enabled(net, (1, 1), "t") is False`` (p2 holds a token) but
        ``enabled(net, (1, 1), "t", usable=(1, 0)) is True`` (the p2 token is
        still in a τ-delay and not usable yet).
        """
        usable = marking if usable is None else usable
        place_index = self._place_index()
        i = self._transition_index(t)
        if not all(marking[place_index[p]] >= w for p, w in self.inputs[i]):
            return False
        if self.inhibitors is not None:
            return all(usable[place_index[p]] == 0 for p in self.inhibitors[i])
        return True

    def fire(self, marking: Marking, t: str) -> Marking:
        """Return ``marking - I(t) + O(t)`` as a new tuple (M3).

        Rebuilds a full |P|-tuple in one pass and never mutates ``marking``
        or the net. Raises ``TransitionNotEnabledError`` if ``t`` is not
        enabled at ``marking`` (input-arc requirement or an inhibitor arc).

        Smoke net: ``net.fire(mu0, "t1") == (5, 5, 2, 5, 4, 3)``.
        """
        if not self.enabled(marking, t):
            raise TransitionNotEnabledError(marking, t)
        place_index = self._place_index()
        i = self._transition_index(t)
        result = list(marking)
        for p, w in self.inputs[i]:
            result[place_index[p]] -= w
        for p, w in self.outputs[i]:
            result[place_index[p]] += w
        return tuple(result)

    def fire_set(self, marking: Marking, ts: Sequence[str]) -> Marking:
        """Fire the set ``ts`` in parallel: one summed application of all of them.

        Every ``t`` in ``ts`` must be enabled at ``marking`` and no two
        transitions of ``ts`` may conflict — that is, share an input place
        (glossary "конфликт") — otherwise ``ConflictError`` is raised. The
        result is ``marking`` minus all I(t) plus all O(t) for ``t`` in
        ``ts``, equal to firing the transitions one by one in any order.

        Example: t1: I={p1}, O={p3}; t2: I={p2}, O={p4} —
        ``fire_set(net, (1, 1, 0, 0), ["t1", "t2"]) == (0, 0, 1, 1)``; if t1
        and t2 both needed p1, ``ConflictError`` would be raised instead.
        """
        indices = [self._transition_index(t) for t in ts]
        for i in indices:
            if not self.enabled(marking, self.transitions[i]):
                raise ConflictError((self.transitions[i],), None)
        for a in range(len(indices)):
            shared_a = {p for p, _ in self.inputs[indices[a]]}
            for b in range(a + 1, len(indices)):
                for p, _ in self.inputs[indices[b]]:
                    if p in shared_a:
                        raise ConflictError(
                            (self.transitions[indices[a]], self.transitions[indices[b]]), p
                        )
        place_index = self._place_index()
        result = list(marking)
        for i in indices:
            for p, w in self.inputs[i]:
                result[place_index[p]] -= w
            for p, w in self.outputs[i]:
                result[place_index[p]] += w
        return tuple(result)

    def active(self, marking: Marking, *, usable: Marking | None = None) -> list[str]:
        """Return transitions enabled at ``marking``, in declared transition order.

        With ``priorities`` set (M8), each conflict group — a maximal set of
        enabled transitions connected by shared input places — keeps only the
        transition(s) with the maximal Pr t (ties keep all); transitions
        outside the group are unaffected.

        Smoke net: ``net.active(mu0) == ["t1", "t2", "t3", "t4", "t5"]``.
        Example: net where t1 and t2 both need p1, priorities (1, 0): at
        marking (1,) ``active`` is ``["t1"]``.
        """
        enabled_ts = [t for t in self.transitions if self.enabled(marking, t, usable=usable)]
        if self.priorities is None:
            return enabled_ts
        priorities = dict(zip(self.transitions, self.priorities, strict=True))
        parent: dict[str, str] = {t: t for t in enabled_ts}

        def find(t: str) -> str:
            root = t
            while parent[root] != root:
                root = parent[root]
            while parent[t] != root:
                parent[t], t = root, parent[t]
            return root

        def union(a: str, b: str) -> None:
            root_a, root_b = find(a), find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        by_place: dict[str, list[str]] = {}
        for t in enabled_ts:
            for p, _ in self.inputs[self._transition_index(t)]:
                by_place.setdefault(p, []).append(t)
        for members in by_place.values():
            for other in members[1:]:
                union(members[0], other)
        max_pr: dict[str, int] = {}
        for t in enabled_ts:
            root = find(t)
            max_pr[root] = max(max_pr[root], priorities[t]) if root in max_pr else priorities[t]
        return [t for t in enabled_ts if priorities[t] == max_pr[find(t)]]

    def incidence(self) -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
        """Return the incidence matrices ``(W−, W+, W)`` (M7), each n×m.

        Row order = ``places``, column order = ``transitions``;
        ``W−[i][j]`` is the weight of the input arc p_i→t_j (0 if none),
        ``W+[i][j]`` the weight of the output arc t_j→p_i, and
        ``W = W+ − W−``.

        TASK-PN-35 (p1→t1, t1→p2, t1→p3, p2→t2, p3→t2, t2→p1, t2→p4):
        ``W− = [[1, 0], [0, 1], [0, 1], [0, 0]]``,
        ``W+ = [[0, 1], [1, 0], [1, 0], [0, 1]]``,
        ``W = [[-1, 1], [1, -1], [1, -1], [0, 1]]``.
        """
        n = len(self.places)
        m = len(self.transitions)
        place_index = self._place_index()
        w_minus = [[0] * m for _ in range(n)]
        w_plus = [[0] * m for _ in range(n)]
        for j in range(m):
            for p, w in self.inputs[j]:
                w_minus[place_index[p]][j] += w
            for p, w in self.outputs[j]:
                w_plus[place_index[p]][j] += w
        w_inc = [[w_plus[i][j] - w_minus[i][j] for j in range(m)] for i in range(n)]
        return (w_minus, w_plus, w_inc)

    def minimal_marking(self, *, parallel: bool = False) -> Marking:
        """Return the minimal marking enabling every transition (M6).

        ``parallel=False``: the per-component maximum of the input
        requirements, ``mu_min[p] = max_j I_w(t_j, p)``; ``parallel=True``:
        the sum of the requirements of all transitions (worst case — every
        transition enabled at the same marking, e.g. for a parallel firing
        set).

        TASK-PN-07 (I(t1)={p1,p1,p2}, I(t2)={p1,p2,p2}):
        ``minimal_marking(net) == (2, 2, 0)`` and
        ``minimal_marking(net, parallel=True) == (3, 3, 0)``.
        TASK-PN-09: ``minimal_marking(net) == (2, 2, 1, 2, 2)``.
        """
        place_index = self._place_index()
        result = [0] * len(self.places)
        for i in range(len(self.transitions)):
            for p, w in self.inputs[i]:
                index = place_index[p]
                if parallel:
                    result[index] += w
                else:
                    result[index] = max(result[index], w)
        return tuple(result)


def enabled(net: PetriNet, m: Marking, t: str, *, usable: Marking | None = None) -> bool:
    """Free-function form of :meth:`PetriNet.enabled` (M2, with ⊣ — M2⊣).

    Example: smoke net — ``enabled(net, (7, 4, 2, 5, 4, 3), "t1") is True``.
    """
    return net.enabled(m, t, usable=usable)


def fire(net: PetriNet, m: Marking, t: str) -> Marking:
    """Free-function form of :meth:`PetriNet.fire` (M3).

    Example: smoke net — ``fire(net, (7, 4, 2, 5, 4, 3), "t1") == (5, 5, 2, 5, 4, 3)``.
    """
    return net.fire(m, t)


def fire_set(net: PetriNet, m: Marking, ts: Sequence[str]) -> Marking:
    """Free-function form of :meth:`PetriNet.fire_set` (parallel firing).

    Example: t1: I={p1}, O={p3}; t2: I={p2}, O={p4} —
    ``fire_set(net, (1, 1, 0, 0), ["t1", "t2"]) == (0, 0, 1, 1)``.
    """
    return net.fire_set(m, ts)


def active(net: PetriNet, m: Marking, *, usable: Marking | None = None) -> list[str]:
    """Free-function form of :meth:`PetriNet.active` (with priorities, M8).

    Example: smoke net —
    ``active(net, (7, 4, 2, 5, 4, 3)) == ["t1", "t2", "t3", "t4", "t5"]``.
    """
    return net.active(m, usable=usable)


def incidence(net: PetriNet) -> tuple[list[list[int]], list[list[int]], list[list[int]]]:
    """Free-function form of :meth:`PetriNet.incidence` (M7).

    Example: TASK-PN-35 —
    ``incidence(net) == ([[1, 0], [0, 1], [0, 1], [0, 0]],
    [[0, 1], [1, 0], [1, 0], [0, 1]], [[-1, 1], [1, -1], [1, -1], [0, 1]])``.
    """
    return net.incidence()


def minimal_marking(net: PetriNet, *, parallel: bool = False) -> Marking:
    """Free-function form of :meth:`PetriNet.minimal_marking` (M6).

    Example: TASK-PN-07 — ``minimal_marking(net, parallel=True) == (3, 3, 0)``.
    """
    return net.minimal_marking(parallel=parallel)
