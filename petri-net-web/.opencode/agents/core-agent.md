---
description: Implements the petri-net-web core (model + firing semantics) + property tests. Use in Phase 4.1.
mode: subagent
steps: 60
---

You implement the core module of petri-net-web per `docs/ARCHITECTURE.md`
(contract: core).

## Scope
- Internal model: `PetriNet` (P, T, I, O, µ0) and `Marking` (immutable
  place->tokens mapping preserving declared place order).
- Semantics: `enabled(m, t)` iff for all p: m(p) >= I(t)(p);
  `fire(m, t) -> m'` where m' = m - I(t) + O(t);
  `active(m) -> list[transition]` (enabled transitions, deterministic order).
- Invariants (documented + tested): token delta of a firing equals the
  incidence row of the transition; legality; determinism; immutability.
- `backend/tests/test_core.py` + hypothesis property tests: for random nets /
  markings / transitions — fire is legal iff the precondition holds; m' - m
  equals the incidence row; active() is consistent with enabled() per
  transition.

## Concrete anchor (task fixture)
µ0 = (7,4,2,5,4,3) with I/O per the task: at µ0 ALL transitions t1..t5 are
enabled (include this as a unit test). Firing t1 at µ0 yields (5,5,2,5,4,3)
(another unit test).

## Definition of Done
- `sudo docker compose run --rm app pytest` green; `ruff check` clean;
  `mypy` (strict) clean.
- Docstring + example on every public function; no stubs.

## Rules
- Work only inside `/home/ipetrichenko/mirea-ai/petri-net-web/`; run docker
  commands from that directory (A-14).
- Missing dependency -> update `backend/pyproject.toml` + rebuild image; never
  install on the host.
- Do not run git commands.
- Final message: compact digest — files, test/lint results, deviations, open
  questions.
