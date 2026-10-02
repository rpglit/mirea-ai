---
description: Implements the petri-net-web properties module (boundedness, safety, liveness L0-L4, reachability/coverability queries, deadlocks, dead transitions, reversibility, deadlock-freedom) + tests. Use in Phase 4.3.
mode: subagent
steps: 60
---

You implement the properties module of petri-net-web per `docs/ARCHITECTURE.md`
(contract: properties; liveness scale per the ADR).

## Scope
- Input: the built reachability graph (bounded) or coverability tree (unbounded,
  ω-semantics per the ADR).
- Properties: per-place boundedness (k) and global; safety; liveness L0–L4
  (per-transition `occurs` + `level` included in the report, net level = min);
  marking reachability query (is marking m reachable from µ0?); coverability
  query (unbounded case); deadlock list; dead-transition list;
  reversibility/home state (µ0 reachable from every reachable marking?);
  deadlock-free.
- Deterministic JSON report: stable key order, machine-readable values plus
  evidence (e.g. the full deadlock list, per-place k).
- Liveness per ADR-0004 (classical scale): L0 dead = never enabled at any
  reachable marking; L1 = enabled at some reachable marking (occurs); L3 =
  some reachable cycle contains a t-edge (one Tarjan SCC pass shared by all
  transitions; on a finite graph L2 <=> L3, so L2 is NEVER emitted); L4 live =
  the backwards closure from the markings where t is enabled covers ALL
  reachable markings (strong, MSU). Per-transition level = L4 if the closure
  covers all, else L3 if the SCC cycle test passes, else L1 if occurs, else
  L0. Net level = min over transitions (order L0 < L1 < L3 < L4); a net at L4
  is deadlock-free.

## Tests (`backend/tests/test_properties.py`)
- Task fixture report must match D-009..D-014 + D-031: 1503 markings, per-place
  k [10,8,16,29,8,10], global k=29, safe=False, 23 deadlocks (exact list in
  D-011), deadlock-free=False, home state=False, dead transitions=[],
  per-transition levels ALL L3 and net liveness level L3 (each t lies on a
  reachable cycle; none L4 — deadlocks break strong liveness).
- >= 3 other nets with hand-computed expectations (unbounded counter:
  unbounded/ω, t level L4; a live loop net: L4; a net with a dead transition +
  live ones: per-transition mix, net level = min).
- Hypothesis: the report is deterministic (same net, two runs -> equal JSON);
  safety implies boundedness; L4 implies deadlock-free; the emitted
  per-transition level is never exactly "L2".

## Definition of Done
- `sudo docker compose run --rm app pytest` green; `ruff check` clean;
  `mypy` (strict) clean.
- No stubs; docstring + example on every public function.

## Rules
- Work only inside `/home/ipetrichenko/mirea-ai/petri-net-web/`; run docker
  commands from that directory (A-14).
- Missing dependency -> update `backend/pyproject.toml` + rebuild image; never
  install on the host.
- Do not run git commands.
- Final message: compact digest — files, test/lint results, deviations, open
  questions.
