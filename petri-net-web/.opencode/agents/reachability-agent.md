---
description: Implements the petri-net-web reachability module (reachability graph + Karp-Miller coverability tree) + tests. Use in Phase 4.2.
mode: subagent
steps: 60
---

You implement the reachability module of petri-net-web per `docs/ARCHITECTURE.md`
(contract: reachability).

## Scope
- Reachability graph for bounded nets: all markings reachable from µ0 plus edges
  (m, t, m'); deterministic node/edge IDs; safety cap from config
  (`REACH_MAX_MARKINGS`, typed error on overflow).
- Karp–Miller coverability tree for unbounded nets: ω-tokens, coverability
  relation (m ≼ m'), guaranteed termination; when to build which structure
  follows the ADR (auto-detect or explicit mode flag per contract).
- Public API per contract, e.g. `build(net) -> ReachabilityGraph |
  CoverabilityTree` with a kind flag.

## Tests (`backend/tests/test_reachability.py`)
- Task fixture: exactly 1503 markings and 4983 edges (DECISIONS_LOG D-008).
- Unbounded counter (1 place, 2 transitions: t_in adds 1, t_out removes 1,
  µ0 = 1): plain reachability hits the cap; the Karp–Miller tree terminates and
  contains an ω node.
- Mutual-exclusion net and producer-consumer net: known structural properties
  (e.g. the mutex net stays 2-bounded; the PC net with bounded buffer is bounded
  — state the expected numbers in the test with a comment explaining where they
  come from).
- Hypothesis: every edge of the built graph is a legal firing; every node is
  reachable from µ0 along its parent chain.

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
