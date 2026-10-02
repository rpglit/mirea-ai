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
- `coverability`: build the Karp–Miller coverability tree. The construction
  always terminates, but the same cap is applied as a safety device (D-034):
  the tree of a *bounded* net with a large state space can be exponentially
  larger than the reachability graph (the path-local subsumption duplicates
  labels across branches), while the tree of an *unbounded* net is small
  because ω compresses it — the cap therefore does not affect any unbounded
  net's result.

Node identity: each node gets a discovery-order index (BFS for the graph,
preorder for the tree), id = `n<index>`; its marking (tuple or ω-marking) is
stored alongside. Edge identity: `n<src>:t<n<dst>` — an edge exists iff
transition `t` fires the source marking to the target. Deterministic order:
transitions are always expanded in declared order, so ids are stable across
runs for the same net.

Karp–Miller expansion (pseudocode; ω = omega):

```
expand(node):                      # node: the leaf being expanded; labels in N^P ∪ (N ∪ {ω})^P
    m = node.marking
    for t in transitions (declared order):
        if not enabled_omega(m, t):   # m(p) >= w for every input arc; ω >= any w
            continue
        m_new = fire_omega(m, t)      # ω - w = ω, ω + w = ω, naturals normally
        anc = node                    # walk the path INCLUDING node itself, up to the root
        discarded = false
        corrected = false
        while anc is not None:
            a = anc.marking
            if a >= m_new:            # a covers m_new (componentwise; ω >= any int)
                discarded = true      # m_new adds no new information
                break
            if m_new > a:             # m_new covers a and is strictly greater somewhere
                for p in places:      # correction with OMEGA PROMOTION
                    if a[p] is not ω and m_new[p] > a[p]:
                        a[p] = ω      # unbounded on this path (not max!)
                corrected = true
            anc = anc.parent          # keep checking m_new against higher ancestors
        if not discarded and not corrected:
            add m_new as a new child of node
```

This is the classical construction with the two decisive rules: a candidate
covered by any node on the path (including the expanding node itself) is
discarded, and a candidate that strictly covers a path node promotes that
node's strictly-smaller natural coordinates to ω (never plain max — max would
let the unbounded counter's root label grow 1, 2, 3, ... forever and break
termination). After a correction the walk continues with the same candidate
against the remaining ancestors.

Termination: (a) every correction promotes at least one new coordinate of that
node to ω (a coordinate that is already ω can never be "strictly exceeded"),
so each node is corrected at most |P| times; (b) firing cannot create ω out of
naturals, so an ω-labeled node has only finitely many ancestors with ω and its
expansion is bounded by (a); (c) a branch of purely natural labels that
grew without bound would eventually contain a label covered by an ancestor on
the path (pigeonhole on the finite set of "tight" natural labels under the
path bound), contradicting the creation rule — hence branches are finite and
the tree terminates.

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
