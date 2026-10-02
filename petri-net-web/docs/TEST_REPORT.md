# Test Report — petri-net-web

|            |                                                                              |
| ---------- | ---------------------------------------------------------------------------- |
| Status     | v1.0 (Phase 5, QA — results)                                                 |
| Date       | 2026-10-02 (all runs)                                                        |
| Verdict    | **ACCEPT** — all exit criteria of `docs/TEST_PLAN.md` satisfied, no open defects |
| Sources    | `docs/TEST_PLAN.md`, `docs/DECISIONS_LOG.md` (D-009…D-014, D-031, D-034, D-035) |

## 1. Environment

- Host: Ubuntu 24.04 VM; Docker 29.1.3 + compose 2.40.3.
- All commands run from the project directory `/home/ipetrichenko/mirea-ai/petri-net-web` with `sudo docker compose ...` (Docker group not set, D-017); nothing installed on the host (NFR-005).

| Service | Image | Notes |
| ------- | ----- | ----- |
| `app`   | built on `python:3.12-slim` | SQLite on `petri-data` volume; healthcheck on `/healthz` |
| `e2e`   | `ubuntu:24.04` + venv + `playwright==1.49.1` + headless Chromium (`install --with-deps`) | `BASE_URL=http://app:8000`; waits for the app healthcheck |

Commands used (the only ones quoted in this report):

| Gate | Command |
| ---- | ------- |
| Build images | `sudo docker compose build` |
| Unit + property suite | `sudo docker compose run --rm app pytest` |
| Lint (ruff) | `sudo docker compose run --rm app ruff check src tests` |
| Types (mypy strict) | `sudo docker compose run --rm app mypy` |
| E2E suite | `sudo docker compose run --rm e2e` (app healthy) |

## 2. Results matrix

| Layer | Command | Result |
| ----- | ------- | ------ |
| unit + property | `sudo docker compose run --rm app pytest` | **80 passed, 0 failed, 0 skipped** (~17 s) |
| lint | `sudo docker compose run --rm app ruff check src tests` | **All checks passed** (rc=0) |
| types | `sudo docker compose run --rm app mypy` (strict, 12 source files) | **Success: no issues found** |
| e2e | `sudo docker compose run --rm e2e` | **5 passed (E2E-1…E2E-5), 0 failed** (~9 s) |
| acceptance cross-check | independent stdlib BFS vs web-path export | **set-equality true, no duplicates**; report values match frozen ground truth (D-009…D-014, D-035) |

The cross-check took the 1503-marking CSV produced through the full web path
(Playwright → UI → API → storage → `/export/markings`) and compared the marking
set to one computed by an independent stdlib implementation (BFS, separate code
path): identical sets, no duplicates. The exported property report matches the
frozen ground truth: 1503/4983 (D-009), global k = 29 (D-010), exactly 23
deadlocks (D-011), per-transition and net level L1 (D-031, D-035), home state
false (D-013), t1 at µ0 → (5, 5, 2, 5, 4, 3) (D-014).

## 3. E2E scenario results

| Scenario | What ran | Result |
| -------- | -------- | ------ |
| E2E-1 text intake | pre-filled smoke text → «Проанализировать» → stats «узлов: 1503, рёбер: 4983»; `#canvas-graph` exactly 1503 nodes rendered; `#canvas-net` 11 nodes (6 places + 5 transitions); properties k = 29, «Безопасна» = нет, level L1, 23 deadlocks; screenshot saved | PASS |
| E2E-2 stepping | at µ0 (p1 (7) / p2 (4)) select t1 + «Шаг» → labels p1 (5) / p2 (5) (marking (5,5,2,5,4,3)); «Отмена» → p1 (7) / p2 (4); «Сброс» → history list empty | PASS |
| E2E-3 exports | CSV: header exactly `p1,p2,p3,p4,p5,p6`, 1504 lines (1 header + 1503 rows), first data row `7,4,2,5,4,3`, no "omega" anywhere; JSON: `global_k` = 29, `liveness.level` = "L1", `deadlocks` = 23 entries | PASS |
| E2E-4 JSON intake | smoke JSON (REQUIREMENTS 5.2) pasted → same frozen numbers: 1503/4983, k = 29, 23 deadlocks, level L1 | PASS |
| E2E-5 session history | created session listed in «История сессий»; click → analysis restored without re-entry: `#graph-stats` shows 1503 nodes again, k = 29 | PASS |

## 4. Defects found and fixed during Phase 5

All were test/infrastructure defects; no product-logic defect was found (the
properties module's SCC/closure logic was correct per D-035).

| # | Defect (cause) | Fix | Where verified |
| - | -------------- | --- | -------------- |
| 1 | Playwright 1.49.1: `wait_for_function` arg/timeout are keyword-only → `TypeError` on positional calls | keyword args in `e2e/conftest.py` | e2e suite green |
| 2 | Runtime CDN dependency (unpkg Cytoscape) hung page load in the offline e2e container | Cytoscape vendored to `frontend/vendor/cytoscape.umd.js`, served by the app; `index.html` now references `/vendor/` | E2E-1 render; suite green |
| 3 | `mcr.microsoft.com/playwright/python:v1.49.1-jammy` lacks the python playwright module, and on a `python:3.12-slim` base `install --with-deps` fails on a Debian/Ubuntu package-name mismatch | e2e base switched to `ubuntu:24.04` + venv + `playwright==1.49.1` + `install --with-deps chromium` | `sudo docker compose build`; e2e run |
| 4 | `wait_analysis` raced the Cytoscape render (stats text appears before the 1503-node canvas render) | wait now requires stats text AND canvas node count AND non-empty step panel | E2E-1 stable |
| 5 | E2E-2 race: labels read right after the step click | explicit `wait_net_label` polling | E2E-2 stable |
| 6 | two invalid Cytoscape selectors/styles: `edge[data(weight) = "1"]` (string-vs-number comparison) and `target-arrow-scale` → console warnings | fixed/removed | E2E-1; no console warnings |

## 5. Acceptance artifacts

| Artifact | Content |
| -------- | ------- |
| `docs/acceptance/acceptance_markings.csv` | 1504 lines (header + 1503 markings, full web path) |
| `docs/acceptance/acceptance_report.json` | full property report of the smoke net |
| `docs/acceptance/acceptance_final.png` | final acceptance screenshot |
| `docs/acceptance/e2e-1-analysis.png` | E2E-1 analysis view (1503-node graph + properties) |

`docs/acceptance/failures/` is empty — no red item produced a failure
screenshot, and no defect remains open.

## 6. Verdict

**ACCEPT.** Every exit criterion of `docs/TEST_PLAN.md` §6 is satisfied: the
unit + property suite (80 passed), ruff, mypy strict, and the e2e suite (5/5)
are green with the counts and durations recorded above; the acceptance
artifacts are in place; the independent cross-check confirms the web path
reproduces the frozen ground truth.

Residual notes (not blockers):

- No load testing — explicitly out of scope (TEST_PLAN §1); NFR-001 is a
  single-run budget, not a concurrency demand.
- Liveness / properties on unbounded nets are the documented ω-approximation
  (A-05 / ADR-0002).
- The bounded-net coverability tree is cap-protected: the smoke net's KM tree
  grows to 1.9M+ nodes in 20 s, so the cap applies as a safety device (D-034).
