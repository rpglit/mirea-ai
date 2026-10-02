# ADR-0004: Liveness scale L0–L4 (classical, per transition)

Status: Accepted (2026-10-02)

## Context

The task requires reporting liveness as "L0–L4". The classical scale
(Murata 1989; confirmed against Wikipedia "Petri net", Liveness section, and
the MSU course material for the L4/"живой" definition) is per-transition:

- **L0 (dead)**: the transition can never fire — it is not enabled at any
  reachable marking.
- **L1 (potentially fireable)**: it fires in at least one firing sequence —
  enabled at some reachable marking.
- **L2 (arbitrarily often)**: for every k >= 1 there is a finite firing
  sequence in which it fires at least k times.
- **L3 (infinitely often)**: there exists an infinite firing sequence in
  which it fires infinitely often.
- **L4 (live)**: from every reachable marking there exists a firing sequence
  reaching a marking where it is enabled (MSU: "любое конечное вычисление
  можно продолжить так, чтобы этот переход сработал").

The net is **Lk-live iff all of its transitions are Lk-live**; the reported
net level is the minimum over transitions (order L0 < L1 < L2 < L3 < L4).
L4-ness of the net implies deadlock-free. The earlier operational partition
in ASSUMPTIONS A-05 (2026-10-02 morning) is superseded by this ADR (D-031).

## Decision

Per-transition levels are computed on the finite reachability graph as
follows (all O((|V|+|E|)·|T|) or better with the SCC pass):

- `occurs(t)`: t enabled at some reachable marking. L0 iff not occurs.
- **L2 / L3 test (one and the same on a finite graph)**: t fires
  arbitrarily often (L2) iff there exists a reachable cycle containing a
  t-edge. Proof sketch: (=>) a reachable cycle with a t-edge looped k times
  gives a sequence firing t k times; looping forever gives an infinite
  sequence. (<=) if t fires arbitrarily often, some marking repeats on the
  way, and the segment between two repeats is a reachable cycle containing a
  t-edge. Implementation: compute the strongly-connected components (Tarjan)
  of the reachability graph once; t passes iff some edge (m --t--> m') has
  m and m' in the same SCC. Since every node is reachable from µ0 by
  construction, "reachable cycle" needs no extra check. On a finite graph
  L2 <=> L3 exactly, so the reported level is **never exactly L2**: a
  transition passing this test is classified L3.
- **L4 test**: backwards closure from the set of markings where t is
  enabled (walk predecessor edges); t is L4 iff the closure covers ALL
  reachable markings.
- Classification: L4 if the L4 test passes; else L3 if the cycle test
  passes; else L1 if occurs; else L0.

For unbounded nets the levels are computed on the Karp–Miller coverability
tree with ω-semantics (t enabled at a marking containing ω whenever the
precondition is eventually satisfiable — ω >= any weight). This
over-approximates, so the report carries `approximation: "omega"`
(FR-009 criterion 5); the L2/L3 cycle test and the L4 closure run on the
tree with the same caveat.

Worked examples:

1. **Smoke net = L3 (net level).** All five transitions occur and each lies
   on a reachable cycle (token circulation through the p1..p6 loop), so each
   is L3; none is L4 — the 23 reachable deadlocks mean that from those
   markings no transition can ever fire again (D-011, D-012).
2. **Loop net = L4.** P={p1}, T={t1}, I(t1)={p1:1}, O(t1)={p1:1},
   µ0=(1,): the only reachable marking is (1,), t1 is enabled there, cycle
   present, closure covers everything → t1 is L4, net L4, deadlock-free.
3. **L2 example (never reported, but the class exists).** Any net where a
   transition fires arbitrarily often but no infinite sequence contains it
   infinitely often; impossible on a finite reachability graph (L2 <=> L3),
   hence unreachable by the implementation — recorded so tests do not expect
   an L2 value.
4. **L0/L1 mix.** P={p1,p2}, T={t1,t2,t3}: I/O of t1: p1 -> p2; t2: p2 ->
   p1; t3: I(t3)={p1:1,p2:1}, O(t3)={p1:1}; µ0=(1,0). Only one token exists,
   so t3 never occurs → t3 = L0; t1, t2 occur and lie on the 2-cycle → L3;
   net level = min = L0.

## Consequences

- The report carries per-transition `{occurs: bool, level: "L0"|"L1"|"L3"|"L4"}`
  plus the net `level` (FR-009 criterion 4 fixture: all five L3, net L3).
- The properties module needs one SCC pass (shared by all transitions) plus
  one backwards closure per transition — linear in (|V|+|E|) per transition,
  negligible for the smoke net (1503/4983).
- Tests must cover at least: smoke net L3 (all transitions), loop net L4,
  the L0/L1-mix net (net level L0), and a net with a dead transition plus a
  live one (per-transition mix). The "never exactly L2" rule is itself a
  property test (hypothesis: classify a random finite graph — L2 never
  emitted).
- L4-implies-deadlock-free becomes a checkable invariant in the report
  validation (FR-009 criterion 3).
