# ADR-0001: Internal data model (immutable)

Status: Accepted (2026-10-02)

**Context**

The backend (FastAPI, Python 3.12) parses user-supplied nets in three
intake formats (text, JSON, form), validates them once (brief §3), and then
runs several algorithms over the same model: BFS reachability construction
(brief §2), Karp–Miller coverability, strong liveness (brief §4), and
step-fire with undo/reset (brief §5–7). All of them test and fire
transitions at markings in tight loops, and the BFS stores visited markings
in sets. The data model must therefore be cheap to fire, usable as a set
key, deterministic in order, and safe to share without mutation. Design
brief §1 pins the shape; this ADR freezes the exact signatures and
semantics.

**Decision**

All model objects are plain immutable dataclass/tuple types: no class
hierarchy, no caches on the model, no in-place updates. Markings are
aligned to the declared place order by integer index, not by name.

```python
from dataclasses import dataclass

Marking = tuple[int, ...]  # m[i] = tokens on places[i]; len(m) == len(net.places)
Arc = tuple[str, int]      # (place, weight), weight >= 1

@dataclass(frozen=True)
class PetriNet:
    places: tuple[str, ...]                  # declared order = index order
    transitions: tuple[str, ...]             # declared order
    inputs: tuple[tuple[Arc, ...], ...]      # inputs[t] = (place, weight) pairs for transitions[t]
    outputs: tuple[tuple[Arc, ...], ...]     # same shape as inputs
    initial_marking: Marking                 # m0, aligned with places

def enabled(net: PetriNet, t: str, m: Marking) -> bool:
    """True iff m[p] >= w for every (p, w) in net.inputs[t]."""

def fire(net: PetriNet, t: str, m: Marking) -> Marking:
    """m' = m - I(t) + O(t); returns a new tuple, never mutates m. O(|P|)."""
```

Semantics (brief §1): `t` is enabled at `m` iff `m[p] >= w` for every
`(p, w)` in `inputs(t)`; firing produces `m' = m - I(t) + O(t)`. A
transition with no input arcs is enabled at every marking. Arc weights are
positive integers; nets that cannot be represented that way are rejected at
validation (brief §3), not at firing time. Both functions run in O(|P|):
the implementation builds place/transition name→index maps once per run and
keeps them outside the model, so `PetriNet` itself stays a plain,
hashable, frozen dataclass.

Why tuples over dicts:

- **Hashability for BFS sets.** `Marking` is a set/dict key in the
  reachability BFS (brief §2, cap `REACH_MAX_MARKINGS`). Tuples hash in
  O(|P|) with no normalization; a `dict[str, int]` marking would need
  `frozenset(m.items())` or a canonical re-sort on every insertion, and key
  order would not be part of the value's identity.
- **Declared order.** `places` is the index basis for every marking, so
  graph nodes, CSV rows (header = place names in declared order, brief §7)
  and the `current_marking` session column (brief §5) line up without a
  stored name→index table.
- **Immutability.** `frozen=True` + nested tuples: the parsed net is shared
  across /graph, /properties and /fire handlers and copied into session
  storage without defensive copies.
- **O(|P|) firing.** Firing rebuilds a tuple of exactly the place length —
  one pass, no dict resizing, no missing-place lookups (a marking never
  has fewer entries than the net has places).

Validation anchors (D-014, smoke net p1..p6 / t1..t5): at
`m0 = (7, 4, 2, 5, 4, 3)` all of `t1..t5` satisfy `enabled(net, t, m0)`,
and `fire(net, "t1", m0) == (5, 5, 2, 5, 4, 3)`. These two facts are the
regression assertions for the core/api test suite.

**Consequences**

- Name uniqueness of places/transitions is guaranteed by schema validation
  (brief §3); code that re-introduces name-keyed dicts for markings is
  rejected in review.
- Determinism comes for free: BFS discovery order, edge ids
  `n<src>:t<n_dst>`, CSV exports and JSON key ordering (brief §7) do not
  depend on dict iteration order.
- Cost: each fire allocates a full |P|-tuple even when a transition touches
  few places. Accepted — with |P| a few dozen and up to 50000 BFS markings
  (D-020), allocation beats the risk of in-place mutation.
- Karp–Miller omega-markings (brief §2) use a parallel type
  `tuple[int | None, ...]` (`None` = ω) in core; the natural-number model
  stays `tuple[int, ...]` and is never widened.
