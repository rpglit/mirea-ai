"""Reachability structures: bounded reachability graph (BFS) and Karp-Miller
coverability tree (ADR-0002)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from petrinet.core import Marking, PetriNet
from petrinet.errors import CapExceededError

OmegaMarking = tuple[int | None, ...]  # None = omega (unbounded place)
MarkingOrOmega = Marking | OmegaMarking  # concrete marking or omega-annotated


@dataclass(frozen=True)
class ReachableStructure:
    """A built reachability structure: labelled nodes, firing edges, stats.

    ``nodes[0]`` is always the initial marking mu0; node ids are
    ``"n<index>"`` in BFS discovery order (graph) or preorder (coverability
    tree), transitions expand in declared order, so the structure is
    deterministic for the same net (ADR-0002).
    """

    kind: Literal["graph", "coverability"]  # which structure was built
    nodes: list[tuple[str, MarkingOrOmega]]  # (node id, marking); nodes[0] is mu0
    edges: list[tuple[str, str, str]]  # (src_id, transition, dst_id)
    stats: dict[str, int]  # {"nodes": N, "edges": M}


def _build_graph(net: PetriNet, cap: int) -> ReachableStructure:
    """Build the bounded reachability graph by BFS over markings.

    Starts at ``net.initial_marking`` (node ``n0``); each popped node is
    expanded along ``net.transitions`` in declared order and every enabled
    firing adds one edge. A firing result not seen yet becomes the next node
    (``"n<index>"`` in discovery order) and is pushed to the queue; when the
    number of distinct markings reaches ``cap`` the build raises
    ``CapExceededError`` instead of adding the next one.

    Smoke net (D-009): 1503 nodes / 4983 edges.
    """
    mu0 = net.initial_marking
    seen: set[Marking] = {mu0}
    node_ids: dict[Marking, str] = {mu0: "n0"}
    nodes: list[tuple[str, MarkingOrOmega]] = [("n0", mu0)]
    edges: list[tuple[str, str, str]] = []
    queue: deque[tuple[str, Marking]] = deque([("n0", mu0)])
    while queue:
        src_id, m = queue.popleft()
        for t in net.transitions:
            if not net.enabled(m, t):
                continue
            m2 = net.fire(m, t)
            if m2 in seen:
                dst_id = node_ids[m2]
            else:
                if len(seen) >= cap:
                    raise CapExceededError(cap)
                dst_id = f"n{len(nodes)}"
                seen.add(m2)
                node_ids[m2] = dst_id
                nodes.append((dst_id, m2))
                queue.append((dst_id, m2))
            edges.append((src_id, t, dst_id))
    return ReachableStructure(
        kind="graph",
        nodes=nodes,
        edges=edges,
        stats={"nodes": len(nodes), "edges": len(edges)},
    )


@dataclass
class _KmNode:
    """Mutable node of the coverability tree under construction (ADR-0002)."""

    marking: OmegaMarking
    parent: int | None
    transition: str | None


def _omega_enabled(
    p_index: dict[str, int], inputs: tuple[tuple[str, int], ...], m: OmegaMarking
) -> bool:
    """Whether every input arc is satisfied (``None`` = omega >= any weight)."""
    for p, w in inputs:
        value = m[p_index[p]]
        if value is not None and value < w:
            return False
    return True


def _omega_fire(
    p_index: dict[str, int],
    inputs: tuple[tuple[str, int], ...],
    outputs: tuple[tuple[str, int], ...],
    m: OmegaMarking,
) -> OmegaMarking:
    """Fire one transition; omega stays omega when any arc touches the place."""
    result = list(m)
    for p, w in inputs:
        i = p_index[p]
        value = result[i]
        if value is not None:
            result[i] = value - w
    for p, w in outputs:
        i = p_index[p]
        value = result[i]
        if value is not None:
            result[i] = value + w
    return tuple(result)


def _covers(anc: OmegaMarking, new: OmegaMarking) -> bool:
    """Whether ``anc`` covers ``new`` (anc >= new, componentwise; omega >= any int).

    A coordinate fails only when ``new`` holds omega and ``anc`` a natural, or
    both are naturals and ``anc`` is smaller.
    """
    for a, n in zip(anc, new, strict=True):
        if n is None:
            if a is not None:
                return False
        elif a is not None and a < n:
            return False
    return True


def _promote(anc: OmegaMarking, new: OmegaMarking) -> OmegaMarking:
    """Correction join (omega promotion, ADR-0002).

    A natural coordinate of ``anc`` strictly exceeded by ``new`` (either by a
    larger natural or by omega) becomes omega; coordinates already omega, or
    not strictly exceeded, keep the ``anc`` value.
    """
    return tuple(
        None if (a is not None and (n is None or n > a)) else a
        for a, n in zip(anc, new, strict=True)
    )


def _build_coverability(net: PetriNet, cap: int) -> ReachableStructure:
    """Build the Karp-Miller coverability tree (ADR-0002).

    Nodes are created in pre-order (creation order); the expanding node's
    whole path (including itself) is checked for each candidate: a candidate
    covered by a path node is discarded, one that strictly covers a path node
    triggers the omega-promoting correction, otherwise it becomes a new
    child. The construction terminates (ADR-0002); the ``cap`` is a safety
    device against the known bounded-net pathology where the tree is
    exponentially larger than the reachability graph (for unbounded nets the
    tree is small because omega compresses it).

    Example (unbounded counter, REQUIREMENTS 5.6: P={p1}, T={t1},
    I(t1)={}, O(t1)={p1:1}, mu0=(1,)): the tree terminates with the root
    label promoted to (None,) — a single omega node.
    """
    p_index = {p: i for i, p in enumerate(net.places)}
    t_index = {t: i for i, t in enumerate(net.transitions)}
    nodes: list[_KmNode] = [_KmNode(marking=net.initial_marking, parent=None, transition=None)]
    i = 0
    while i < len(nodes):
        base = i
        node = nodes[i]
        i += 1
        m = node.marking
        for t in net.transitions:
            ti = t_index[t]
            in_arcs = net.inputs[ti]
            out_arcs = net.outputs[ti]
            if not _omega_enabled(p_index, in_arcs, m):
                continue
            m2 = _omega_fire(p_index, in_arcs, out_arcs, m)
            j: int | None = base
            discarded = False
            corrected = False
            while j is not None:
                a = nodes[j].marking
                if _covers(a, m2):
                    discarded = True
                    break
                if _covers(m2, a) and m2 != a:
                    nodes[j].marking = _promote(a, m2)
                    corrected = True
                j = nodes[j].parent
            if not discarded and not corrected:
                if len(nodes) >= cap:
                    raise CapExceededError(cap)
                nodes.append(_KmNode(marking=m2, parent=base, transition=t))
    nodes_out = [(f"n{k}", node.marking) for k, node in enumerate(nodes)]
    edges_out = [
        (f"n{node.parent}", node.transition, f"n{k}")
        for k, node in enumerate(nodes)
        if node.parent is not None and node.transition is not None
    ]
    return ReachableStructure(
        kind="coverability",
        nodes=nodes_out,
        edges=edges_out,
        stats={"nodes": len(nodes), "edges": len(edges_out)},
    )


def build(
    net: PetriNet,
    mode: Literal["auto", "bounded", "coverability"] = "auto",
    cap: int = 50000,
) -> ReachableStructure:
    """Build the reachability structure for ``net`` (ADR-0002).

    ``mode``:

    - ``"auto"`` / ``"bounded"``: BFS reachability graph with a hard cap
      ``cap`` on the number of distinct markings; exceeding it raises
      ``CapExceededError`` (413, suggestion ``"coverability"``).
    - ``"coverability"``: Karp-Miller coverability tree with the
      ancestor-correction step (omega promotion where the candidate strictly
      exceeds a path node); omega dominates naturals, so the construction
      always terminates. The same ``cap`` applies as a safety device: the
      tree of a bounded net with a large state space can be exponentially
      larger than the reachability graph (D-034), while the tree of an
      unbounded net is small because omega compresses it.

    Smoke (D-009): ``build(smoke_net(), "auto")`` -> kind ``"graph"``,
    ``stats`` ``{"nodes": 1503, "edges": 4983}``. The unbounded counter net
    (REQUIREMENTS 5.6) with ``mode="coverability"`` terminates with a single
    omega node.
    """
    if mode in ("auto", "bounded"):
        return _build_graph(net, cap)
    return _build_coverability(net, cap)
