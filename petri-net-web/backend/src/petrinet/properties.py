"""Property analysis over reachability structures (FR-007..FR-014)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from petrinet.core import Marking, PetriNet
from petrinet.reachability import MarkingOrOmega, ReachableStructure

# classical scale (ADR-0004); L2 never emitted on a finite graph
LivenessLevel = Literal["L0", "L1", "L3", "L4"]


@dataclass(frozen=True)
class TransitionLiveness:
    """Liveness of one transition (ADR-0004): whether it occurs and its level."""

    occurs: bool
    level: LivenessLevel  # L0 dead / L1 occurs / L3 cycle-with-t / L4 live (strong)


@dataclass(frozen=True)
class Liveness:
    """Per-transition liveness plus the net level (min over transitions)."""

    level: LivenessLevel  # net level = min over transitions (order L0<L1<L3<L4)
    transitions: dict[str, TransitionLiveness]


@dataclass(frozen=True)
class Report:
    """Full property report (FR-007..FR-014) with deterministic ordering (D-022)."""

    per_place_k: dict[str, int | None]  # place -> k_p; None = unbounded (omega)
    global_k: int | None  # max of k_p; None = net unbounded
    bounded: bool  # all places bounded (global_k is not None)
    safe: bool  # 1-bounded (all k_p <= 1)
    liveness: Liveness
    deadlocks: list[MarkingOrOmega]  # tree labels may contain omega (None)
    dead_transitions: list[str]
    home_state: bool
    deadlock_free: bool
    approximation: Literal[None, "omega"]
    stats: dict[str, int]


def _level_rank(level: LivenessLevel) -> int:
    """Rank of a liveness level in the order L0 < L1 < L3 < L4.

    L2 is skipped: rank 2 is reserved for it but never emitted, because on a
    finite reachability graph L2 and L3 coincide (ADR-0004).
    """
    return {"L0": 0, "L1": 1, "L3": 3, "L4": 4}[level]


def _tarjan_scc(node_ids: list[str], edges: list[tuple[str, str, str]]) -> dict[str, int]:
    """Strongly-connected components of the directed firing graph (iterative Tarjan).

    ``edges`` are ``(src, transition, dst)`` triples used strictly directed as
    ``src -> dst``. Returns a component id per node (ids assigned in
    completion order). The iterative form keeps an explicit work stack, so
    graphs of 1500+ nodes run without recursion-limit issues; the single
    shared pass serves the cycle test of every transition (ADR-0004).
    """
    successors: dict[str, list[str]] = {n: [] for n in node_ids}
    for src, _t, dst in edges:
        successors[src].append(dst)

    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    component: dict[str, int] = {}
    counter = 0
    next_component = 0

    for start in node_ids:
        if start in index:
            continue
        index[start] = counter
        lowlink[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        work: list[tuple[str, int]] = [(start, 0)]
        while work:
            node, pos = work[-1]
            children = successors[node]
            if pos < len(children):
                work[-1] = (node, pos + 1)
                child = children[pos]
                if child not in index:
                    index[child] = counter
                    lowlink[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, 0))
                elif child in on_stack and index[child] < lowlink[node]:
                    lowlink[node] = index[child]
            else:
                work.pop()
                if lowlink[node] == index[node]:
                    comp = next_component
                    next_component += 1
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component[member] = comp
                        if member == node:
                            break
                if work:
                    parent = work[-1][0]
                    if lowlink[node] < lowlink[parent]:
                        lowlink[parent] = lowlink[node]
    return component


def _cycle_edges(
    net: PetriNet, structure: ReachableStructure, scc: dict[str, int]
) -> dict[str, bool]:
    """Which transitions lie on a reachable cycle (the L2/L3 test, ADR-0004).

    Returns ``{t: True}`` iff some edge ``(src, t, dst)`` has both endpoints
    in the same strongly-connected component; every node of the structure is
    reachable from mu0 by construction, so the cycle itself is reachable.
    """
    on_cycle = {t: False for t in net.transitions}
    for src, t, dst in structure.edges:
        if not on_cycle[t] and scc[src] == scc[dst]:
            on_cycle[t] = True
    return on_cycle


def _backwards_closure(structure: ReachableStructure, start_ids: set[str]) -> set[str]:
    """All node ids that can reach any id in ``start_ids`` (BFS over reversed edges).

    The reverse adjacency is built once per call. Used for the L4 test
    (start = one transition's enablement set) and the home-state test
    (start = the nodes carrying mu0).
    """
    predecessors: dict[str, list[str]] = {nid: [] for nid, _m in structure.nodes}
    for src, _t, dst in structure.edges:
        predecessors[dst].append(src)
    seen: set[str] = set(start_ids)
    queue: list[str] = list(start_ids)
    head = 0
    while head < len(queue):
        node = queue[head]
        head += 1
        for pred in predecessors[node]:
            if pred not in seen:
                seen.add(pred)
                queue.append(pred)
    return seen


def _enabled_ids(net: PetriNet, structure: ReachableStructure) -> dict[str, set[str]]:
    """Node ids at which each transition is enabled (concrete markings, GRAPH kind).

    The graph builder emits exactly one edge per (node, enabled transition)
    pair, so t is enabled at precisely the sources of its t-edges; node
    labels here are concrete markings, unlike the coverability tree.
    """
    enabled: dict[str, set[str]] = {t: set() for t in net.transitions}
    for src, t, _dst in structure.edges:
        enabled[t].add(src)
    return enabled


def _omega_enabled_marking(net: PetriNet, t: str, m: MarkingOrOmega) -> bool:
    """Whether transition ``t`` is omega-enabled at marking ``m`` (ADR-0002).

    True iff for every input arc ``(p, w)`` the marking holds omega (``None``)
    or at least ``w`` tokens; a transition without input arcs is enabled at
    every marking. Self-contained: no reachability internals involved.
    """
    place_index = dict(zip(net.places, range(len(net.places)), strict=True))
    for p, w in net.inputs[net.transitions.index(t)]:
        value = m[place_index[p]]
        if value is not None and value < w:
            return False
    return True


def _analyze_graph(net: PetriNet, structure: ReachableStructure) -> Report:
    """Exact property set over a reachability graph (FR-007..FR-014).

    Smoke anchors (D-010..D-013, D-031): per_place_k p1..p6 = 10, 8, 16, 29,
    8, 10; global_k = 29; bounded = True; safe = False; liveness level "L3"
    with all five transitions (occurs=True, level="L3"); deadlocks = the 23
    lexicographically sorted markings (D-011, D-022); dead_transitions = [];
    home_state = False; deadlock_free = False.
    """
    node_ids = [nid for nid, _m in structure.nodes]
    all_ids: set[str] = set(node_ids)

    per_place_k: dict[str, int | None] = {}
    global_k: int | None = None
    for i, p in enumerate(net.places):
        best = 0
        for _nid, m in structure.nodes:
            v = m[i]
            if v is not None and v > best:
                best = v
        per_place_k[p] = best
        if global_k is None or best > global_k:
            global_k = best
    bounded = global_k is not None
    safe = global_k is not None and global_k <= 1

    enabled = _enabled_ids(net, structure)
    enabled_union: set[str] = set()
    for t in net.transitions:
        enabled_union |= enabled[t]
    deadlocks = sorted(m for _nid, m in structure.nodes if _nid not in enabled_union)
    dead_transitions = [t for t in net.transitions if not enabled[t]]

    scc = _tarjan_scc(node_ids, structure.edges)
    on_cycle = _cycle_edges(net, structure, scc)
    per_transition: dict[str, TransitionLiveness] = {}
    for t in net.transitions:
        occurs = bool(enabled[t])
        l4 = _backwards_closure(structure, enabled[t]) == all_ids
        if l4:
            level: LivenessLevel = "L4"
        elif on_cycle[t]:
            level = "L3"
        elif occurs:
            level = "L1"
        else:
            level = "L0"
        per_transition[t] = TransitionLiveness(occurs=occurs, level=level)
    net_level = min(per_transition.values(), key=lambda tl: _level_rank(tl.level)).level

    home_starts = {nid for nid, m in structure.nodes if m == net.initial_marking}
    home_state = _backwards_closure(structure, home_starts) == all_ids

    return Report(
        per_place_k=per_place_k,
        global_k=global_k,
        bounded=bounded,
        safe=safe,
        liveness=Liveness(level=net_level, transitions=per_transition),
        deadlocks=deadlocks,
        dead_transitions=dead_transitions,
        home_state=home_state,
        deadlock_free=not deadlocks,
        approximation=None,
        stats=structure.stats,
    )


def _analyze_coverability(net: PetriNet, structure: ReachableStructure) -> Report:
    """Omega-approximate property set over a Karp-Miller tree (ADR-0002, ADR-0004).

    A place holding omega (``None``) anywhere in the tree is unbounded (k =
    None). Enablement, deadlocks, liveness and home state use omega semantics
    (omega dominates any weight), so every answer is an over-approximation;
    the report carries ``approximation="omega"`` (FR-009 criterion 5).
    """
    node_ids = [nid for nid, _m in structure.nodes]
    all_ids: set[str] = set(node_ids)

    per_place_k: dict[str, int | None] = {}
    for i, p in enumerate(net.places):
        best = 0
        unbounded = False
        for _nid, m in structure.nodes:
            v = m[i]
            if v is None:
                unbounded = True
                break
            if v > best:
                best = v
        per_place_k[p] = None if unbounded else best
    concrete = [k for k in per_place_k.values() if k is not None]
    global_k = max(concrete, default=None) if len(concrete) == len(per_place_k) else None
    bounded = global_k is not None
    safe = global_k is not None and global_k <= 1

    enabled_omega: dict[str, set[str]] = {
        t: {nid for nid, m in structure.nodes if _omega_enabled_marking(net, t, m)}
        for t in net.transitions
    }
    enabled_union: set[str] = set()
    for t in net.transitions:
        enabled_union |= enabled_omega[t]
    deadlocks = sorted(
        (m for _nid, m in structure.nodes if _nid not in enabled_union),
        key=lambda m: tuple((1, 0) if v is None else (0, v) for v in m),
    )
    dead_transitions = [t for t in net.transitions if not enabled_omega[t]]

    scc = _tarjan_scc(node_ids, structure.edges)
    on_cycle = _cycle_edges(net, structure, scc)
    per_transition: dict[str, TransitionLiveness] = {}
    for t in net.transitions:
        occurs = bool(enabled_omega[t])
        l4 = _backwards_closure(structure, enabled_omega[t]) == all_ids
        if l4:
            level: LivenessLevel = "L4"
        elif on_cycle[t]:
            level = "L3"
        elif occurs:
            level = "L1"
        else:
            level = "L0"
        per_transition[t] = TransitionLiveness(occurs=occurs, level=level)
    net_level = min(per_transition.values(), key=lambda tl: _level_rank(tl.level)).level

    home_starts = {nid for nid, m in structure.nodes if m == net.initial_marking}
    home_state = _backwards_closure(structure, home_starts) == all_ids

    return Report(
        per_place_k=per_place_k,
        global_k=global_k,
        bounded=bounded,
        safe=safe,
        liveness=Liveness(level=net_level, transitions=per_transition),
        deadlocks=deadlocks,
        dead_transitions=dead_transitions,
        home_state=home_state,
        deadlock_free=not deadlocks,
        approximation="omega",
        stats=structure.stats,
    )


def analyze(net: PetriNet, structure: ReachableStructure) -> Report:
    """Compute the full property set over the stored structure (FR-007..FR-014).

    Dispatches on ``structure.kind``: a reachability graph is answered
    exactly; the coverability tree is answered with the omega approximation
    (ADR-0002).

    Smoke (D-010..D-013, D-031): per_place_k p1..p6 = 10, 8, 16, 29, 8, 10,
    global_k = 29, bounded = True, safe = False, liveness "L3" (all five
    transitions occurs=True / level="L3"), 23 deadlocks (D-011, D-022 order),
    dead_transitions = [], home_state = False, deadlock_free = False.
    """
    if structure.kind == "graph":
        return _analyze_graph(net, structure)
    return _analyze_coverability(net, structure)


def is_reachable(
    net: PetriNet, structure: ReachableStructure, target: Marking
) -> bool | None:
    """Exact reachability query (FR-010).

    Reachability graph: True iff ``target`` is one of the node markings.
    Coverability tree: None — exact reachability is undecidable in general;
    use ``is_coverable`` instead.

    Smoke: ``is_reachable(net, graph, (7, 4, 2, 5, 4, 3)) is True``;
    ``is_reachable(net, graph, (11, 0, 0, 0, 0, 0)) is False``.
    """
    if structure.kind == "coverability":
        return None
    return target in {m for _nid, m in structure.nodes}


def is_coverable(
    net: PetriNet, structure: ReachableStructure, target: Marking
) -> bool | None:
    """Coverability query (FR-010).

    True iff some structure marking ``m`` has ``m[i] >= target[i]`` for every
    place; an omega coordinate (``None``) dominates any natural, so it always
    covers. Answered from either structure — on a coverability tree the
    answer is exact in the coverability sense (omega approximation, ADR-0002).

    Always returns a concrete bool for both structure kinds; the ``None`` in
    the signature is reserved for future undecidable query variants (exact
    reachability on a tree is the one answered as ``None`` by
    ``is_reachable``).

    Smoke: (7, 4, 2, 5, 4, 3) True; (0, 0, 0, 0, 0, 0) True; (11, 0, 0, 0, 0, 0)
    False (p1 never exceeds 10).
    """
    for _nid, m in structure.nodes:
        if all(v is None or v >= t for v, t in zip(m, target, strict=True)):
            return True
    return False
