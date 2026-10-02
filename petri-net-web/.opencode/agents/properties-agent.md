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
  (per-transition occurs/live flags included in the report); marking
  reachability query (is marking m reachable from µ0?); coverability query
  (unbounded case); deadlock list; dead-transition list; reversibility/home
  state (µ0 reachable from every reachable marking?); deadlock-free.
- Deterministic JSON report: stable key order, machine-readable values plus
  evidence (e.g. the full deadlock list, per-place k).
- Liveness definition (MSU course material, confirmed): a transition t is live
  iff for every reachable marking M there exists a marking K, M ->* K, with t
  enabled at K. The L0–L4 partition per ASSUMPTIONS A-05.

## Tests (`backend/tests/test_properties.py`)
- Task fixture report must match D-008: 1503 markings, per-place k
  [10,8,16,29,8,10], global k=29, safe=False, 23 deadlocks (exact list in
  D-008), deadlock-free=False, home state=False, dead transitions=[], liveness
  level L1 (all occur, none live under the strong definition).
- >= 3 other nets with hand-computed expectations (unbounded counter:
  unbounded/ω; a live net, e.g. a simple loop: L4; a dead net: L0).
- Hypothesis: the report is deterministic (same net, two runs -> equal JSON);
  safety implies boundedness; L4 implies deadlock-free.

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
