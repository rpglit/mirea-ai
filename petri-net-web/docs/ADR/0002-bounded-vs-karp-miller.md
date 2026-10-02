# ADR-0002: Bounded reachability graph vs Karp–Miller coverability tree

Status: Accepted (2026-10-02)

## Context

The reachability set R(µ0) is finite iff the net is bounded (ASSUMPTIONS A-03;
MSU theorem: bounded ⇔ R finite). Building the full reachability graph is the
default analysis structure: every property in FR-007..FR-014 is exact on it.
Unbounded nets make R infinite, so the full graph cannot be built; the
Karp–Miller coverability tree is the standard finite abstraction whose nodes
are ω-markings and whose edges are firings, with the coverability relation
`m ≼ m'` (m(p) ≤ m'(p) for all p, ω ≥ any natural) in place of equality.

User input is arbitrary, so the API must handle both worlds deterministically
and never hang or OOM (NFR-001, NFR-002).

## Decision

The build endpoint accepts a `mode` with three values:

- `auto` (default): build the bounded reachability graph; if the node count
  exceeds `REACH_MAX_MARKINGS` (default 50000), abort with the typed
  `CapExceededError` (HTTP 413). The error body carries
  `details.suggestion: "coverability"` so the UI can offer the fallback.
- `bounded`: same, but the cap is never silently relaxed; hitting it is always
  an error.
- `coverability`: build the Karp–Miller coverability tree (always terminates,
  no cap needed).

Node identity: each node gets a discovery-order index (BFS for the graph,
preorder for the tree), id = `n<index>`; its marking (tuple or ω-marking) is
stored alongside. Edge identity: `n<src>:t<n<dst>` — an edge exists iff
transition `t` fires the source marking to the target. Deterministic order:
transitions are always expanded in declared order, so ids are stable across
runs for the same net.

Karp–Miller expansion (pseudocode; ω = omega):

```
expand(node):
    m = node.marking                      # tuple over P, entries in N or {omega}
    for t in transitions (declared order):
        if not enabled(m, t):             # enabled: m(p) >= w for all input arcs (omega >= any w)
            continue
        m_new = fire(m, t)                # componentwise, omega - w = omega, omega + w = omega
        anc = node
        while anc is not None:                    # walk up to the root
            if anc.marking == m_new:              # already explored under this path
                return
            if covers(m_new, anc.marking):        # m_new(p) >= anc(p) for all p
                merge: for each p with m_new(p) > anc(p) (or omega):
                           anc.marking(p) = max(anc.marking(p), m_new(p))  # omega wins
                re-apply the correction to anc's ancestors (loop continues)
                node.marking = corrected node marking along the path  # standard KM path update
                return
            anc = anc.parent
        if m_new not in node.children_by_marking:
            add child node(m_new) under node
        # else: already explored, skip
```

This is the classical construction: a child that is covered by an ancestor is
not added as a new node; instead the ancestor's marking is raised
(componentwise max, introducing ω where the child strictly exceeds it) and the
correction is re-checked upward.

Termination: each correction step strictly increases the multiset of coordinates
that are ω, or — with the ω-set fixed — strictly increases a natural coordinate
value while a higher coordinate (in a fixed well-order of coordinates) was
already raised; the state space of "correction progress" is well-founded, so
the construction halts on a finite tree with ≤ (|P|+1)·(cap+1)^|P| possible
marking vectors in practice bounded far below.

Consequences for properties (FR-007..FR-014): on a coverability tree,
ω-markings mean "arbitrarily many tokens". Boundedness: a place with an ω
anywhere in the tree is unbounded; per-place k is reported as `ω`/null.
Liveness levels are computed with the ω-semantics: a transition is enabled at a
marking containing ω whenever the natural-token precondition would be
eventually satisfiable (ω ≥ any weight) — this over-approximates liveness, so
the report carries `approximation: "omega"` (REQUIREMENTS FR-009 criterion 5).
Reachability queries on the tree answer coverability (m ≼ node-marking) and
are labeled accordingly; exact reachability is not decidable in general.
Deadlocks/dead transitions/home state are exact only on the bounded graph and
are marked `approximation` on the tree.

## Consequences

- `auto` keeps the common case exact and simple; the cap is a hard safety
  device (NFR-002) with a typed, machine-readable escalation path to
  `coverability`.
- The tree construction must be implemented carefully (the correction step is
  the classic bug source); tests must include the unbounded counter (1 place,
  add/remove transitions) where the tree terminates with a single ω node
  (see REQUIREMENTS §5 secondary fixture), plus mutual-exclusion and
  producer-consumer nets (FR-006 criteria).
- Node/edge ids are stable, which makes the reachability canvas and CSV export
  deterministic (FR-016, FR-021).
- Clients must read the `approximation` field in reports and in query answers
  to avoid presenting ω-results as exact (UI: a visible caveat badge).
