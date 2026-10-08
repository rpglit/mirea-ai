"""Property analysis over reachability structures (FR-007..FR-014, M5–M7)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from petrinet.core import Marking, PetriNet, fire, incidence, minimal_marking
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
    conservative: dict[str, object]  # M5, always computed: per-transition in/out + constant sum
    verdict: str | None  # M5: "живая"/"тупиковая"/"частичнотупиковая"; None for coverability
    mu_min: list[int] | None = None  # M6: filled only by analyze(..., with_mu_min=True)


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


def _has_cycle(scc: dict[str, int], edges: list[tuple[str, str, str]]) -> bool:
    """Whether some firing edge lies inside one strongly-connected component.

    Reuses the single shared SCC pass (``_tarjan_scc``): a self-loop is an
    in-component edge as well, so this is exactly the "the reachability graph
    is a DAG" test of the M5 classification.
    """
    return any(scc[src] == scc[dst] for src, _t, dst in edges)


def _classification(level: LivenessLevel, has_cycle: bool) -> str:
    """The M5 three-class verdict over a reachability graph.

    «живая» ⇔ net level L4 (from any reachable marking any transition can
    fire); «тупиковая» ⇔ the graph is a DAG (no cycles — every firing chain
    is finite, so deadlocking markings necessarily exist); «частичнотупиковая»
    ⇔ neither (cycles exist — some transitions run forever, but not all are
    live).
    """
    if level == "L4":
        return "живая"
    if not has_cycle:
        return "тупиковая"
    return "частичнотупиковая"


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

    Smoke anchors (D-010..D-013, D-031, D-035): per_place_k p1..p6 = 10, 8,
    16, 29, 8, 10; global_k = 29; bounded = True; safe = False; liveness
    level "L1" with all five transitions (occurs=True, level="L1"); deadlocks
    = the 23 lexicographically sorted markings (D-011, D-022);
    dead_transitions = []; home_state = False; deadlock_free = False;
    verdict = "тупиковая" (the graph is a DAG, D-035); conservative = False
    (t1: in 2 / out 1).
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
        conservative=conservative(net, structure),
        verdict=_classification(net_level, _has_cycle(scc, structure.edges)),
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
        conservative=conservative(net, structure),
        verdict=None,
    )


def conservative(net: PetriNet, structure: ReachableStructure) -> dict[str, object]:
    """Conservativity per the handbook (M5) — both definitions at once.

    ``per_transition[t]`` is ``{"in": Σw(I(t)), "out": Σw(O(t)), "equal": ...}``;
    ``constant_sum`` is True iff the total token count is identical at every
    node of the structure (an omega coordinate breaks the equality — the sum
    is not a constant over the structure); ``conservative`` requires BOTH the
    per-transition balance and the constant sum.

    Example 8 (cycle p1→t1→p2→t2→p1, µ=(1,0)): both transitions balanced,
    sum 1 at every node → conservative True. TASK-PN-09: t1 in 3 / out 2 and
    t3 in 4 / out 2 → False. Smoke net: t1 in 2 / out 1 → False.
    """
    per_transition: dict[str, dict[str, object]] = {}
    for i, t in enumerate(net.transitions):
        w_in = sum(w for _p, w in net.inputs[i])
        w_out = sum(w for _p, w in net.outputs[i])
        per_transition[t] = {"in": w_in, "out": w_out, "equal": w_in == w_out}
    sums: set[int] = set()
    constant_sum = True
    for _nid, m in structure.nodes:
        total = 0
        for value in m:
            if value is None:
                constant_sum = False
                break
            total += value
        if not constant_sum:
            break
        sums.add(total)
    constant = constant_sum and len(sums) <= 1
    balanced = all(entry["equal"] for entry in per_transition.values())
    return {
        "per_transition": per_transition,
        "constant_sum": constant,
        "conservative": balanced and constant,
    }


def sequence_report(net: PetriNet, marking: Marking, sigma: Sequence[str]) -> dict[str, object]:
    """Matrix-method trace of a firing sequence σ (M7, handbook formula (1)).

    Fires σ step by step from ``marking`` (core.fire) reporting each step as
    ``{"transition", "from", "to", "enabled"}``; the first non-executable step
    carries ``"to": None`` and is recorded in ``failed_at`` (1-based), after
    which the trace stops. ``v`` is v(σ) — the occurrence count of every
    transition in declared order (0 for transitions absent from σ). When the
    whole sequence is executable, ``mu_prime`` is ``marking + W·v(σ)`` (the
    W = W+ − W− incidence from core.incidence) — equal to the step-by-step
    result; otherwise it is None.

    Raises ``ValueError`` for a transition not in the net or a marking whose
    length differs from the number of places.

    TASK-PN-05 (smoke net, µ=(7,4,2,5,4,3), σ=t1…t5): executable,
    mu_prime=(5,3,4,6,3,3), v=(1,1,1,1,1). TASK-PN-17 (µ=(2,1,1),
    σ=t1,t1,t2,t2): executable=False, failed_at=4. TASK-PN-35 (µ=(1,0,2,1),
    σ=t1,t2,t1): executable, v=(2,1), mu_prime=(0,1,3,2).
    """
    if len(marking) != len(net.places):
        raise ValueError(f"marking of length {len(marking)} for {len(net.places)} places")
    known = set(net.transitions)
    for t in sigma:
        if t not in known:
            raise ValueError(f"unknown transition '{t}'")
    _w_minus, _w_plus, w_inc = incidence(net)
    position = {t: i for i, t in enumerate(net.transitions)}
    v = [0] * len(net.transitions)
    for t in sigma:
        v[position[t]] += 1
    steps: list[dict[str, object]] = []
    current: Marking = tuple(marking)
    executable = True
    failed_at: int | None = None
    for step_no, t in enumerate(sigma, start=1):
        if net.enabled(current, t):
            nxt = fire(net, current, t)
            steps.append({"transition": t, "from": list(current), "to": list(nxt), "enabled": True})
            current = nxt
        else:
            steps.append({"transition": t, "from": list(current), "to": None, "enabled": False})
            executable = False
            failed_at = step_no
            break
    mu_prime: list[int] | None = None
    if executable:
        mu_prime = [
            marking[i] + sum(w_inc[i][j] * v[j] for j in range(len(net.transitions)))
            for i in range(len(net.places))
        ]
    return {
        "steps": steps,
        "v": v,
        "mu_prime": mu_prime,
        "executable": executable,
        "failed_at": failed_at,
    }


def verdict(structure: ReachableStructure, report: Report) -> str | None:
    """Handbook classification (M5) of a reachability structure.

    Three mutually exclusive classes: «живая» ⇔ ``report.liveness.level`` is
    L4 (from any reachable marking any transition can fire); «тупиковая» ⇔
    the reachability graph is a DAG (no cycles — every firing chain is
    finite; deadlocking markings necessarily exist); «частичнотупиковая» ⇔
    neither (cycles exist — some transitions work forever, but not all are
    live). The cycle test reuses the shared SCC pass over ``structure.edges``.

    NOTE: «тупиковая» is NOT "deadlocks ≠ ∅" — a cyclic net without any
    deadlocking marking (e.g. the two-component net, DECISIONS_LOG D-052) is
    «частичнотупиковая». For a coverability structure (omega nodes) the
    verdict is undetermined: None.
    """
    if structure.kind == "coverability":
        return None
    node_ids = [nid for nid, _m in structure.nodes]
    scc = _tarjan_scc(node_ids, structure.edges)
    return _classification(report.liveness.level, _has_cycle(scc, structure.edges))


def analyze(
    net: PetriNet,
    structure: ReachableStructure,
    *,
    with_mu_min: bool = False,
    parallel_mu_min: bool = False,
) -> Report:
    """Compute the full property set over the stored structure (FR-007..FR-014, M5–M7).

    Dispatches on ``structure.kind``: a reachability graph is answered
    exactly; the coverability tree is answered with the omega approximation
    (ADR-0002). ``conservative`` (M5) is computed for both kinds (it is
    cheap); ``verdict`` (M5, three-class) is None on a coverability tree.
    ``with_mu_min`` fills ``Report.mu_min`` via core.minimal_marking (M6);
    ``parallel_mu_min`` selects the parallel variant (sum of all input
    requirements — the worst case of every transition enabled at once).

    Smoke (D-010..D-013, D-031, D-035): per_place_k p1..p6 = 10, 8, 16, 29,
    8, 10, global_k = 29, bounded = True, safe = False, liveness "L1" (all
    five transitions occurs=True / level="L1"), 23 deadlocks (D-011, D-022
    order), dead_transitions = [], home_state = False, deadlock_free = False,
    verdict "тупиковая" (DAG), conservative False.
    """
    if structure.kind == "graph":
        report = _analyze_graph(net, structure)
    else:
        report = _analyze_coverability(net, structure)
    if not with_mu_min:
        return report
    return replace(report, mu_min=list(minimal_marking(net, parallel=parallel_mu_min)))


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
