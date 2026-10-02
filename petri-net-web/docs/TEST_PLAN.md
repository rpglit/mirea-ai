# Test Plan — petri-net-web

|            |                                                                  |
| ---------- | ---------------------------------------------------------------- |
| Status     | v1.0 (Phase 5, QA)                                               |
| Date       | 2026-10-02                                                       |
| Sources    | `docs/REQUIREMENTS.md` (FR/NFR + fixtures §5.1–5.6), `docs/DECISIONS_LOG.md` (D-009…D-014, D-031, D-034, D-035), `.opencode/agents/qa-agent.md`, `docker-compose.yml`, `README.md` (Checks) |

This plan is written before running tests (QA Definition of Done). The
matching results go to `docs/TEST_REPORT.md`.

## 1. Purpose and scope

### In scope

- **Backend domain modules** (`backend/src/petrinet/`): core semantics
  (S = (P, T, I, O, µ0), enablement, firing, A-06 order), the three parsers
  (raw text, JSON, interactive form), reachability graph + Karp–Miller
  coverability construction, and the property set (boundedness, safety,
  liveness L0–L4, reachability/coverability queries, deadlocks, dead
  transitions, home state, deadlock-free).
- **API** (FastAPI): all endpoints (intake/parse, `/graph`, `/properties`,
  `/fire`, `/undo`, `/reset`, `/goto`, `/reachable`, `/coverable`, exports
  CSV/JSON, session history list/load/delete, `/healthz`), typed errors
  (409/413/422/404 contracts), exercised with the in-process TestClient.
- **UI end-to-end** (Playwright, headless Chromium): intake paths,
  visualization, stepping, exports, session history — scenarios E2E-1…E2E-5
  (Section 5), driven against the real app container.
- **Frozen acceptance fixtures** (Section 4): every expected number is
  anchored to REQUIREMENTS §5 / DECISIONS_LOG ground truth; any deviation is
  a defect, not a plan mismatch.

### Out of scope

- CI pipelines (NFR-008): gates are run manually in containers; absence of
  CI is not a defect.
- Load / user-concurrency testing (no NFR demands it; NFR-001 is verified by
  a single-container timing check instead, see Section 7).
- Security audit: no auth exists (single anonymous session), no secrets,
  no injection testing required.
- Link sharing / public URLs: the feature does not exist (NFR-009); nothing
  to test.
- Dark theme / advanced styling (NFR-007).
- Host-environment behavior: everything runs in containers (NFR-005, A-14).

## 2. Test environment

Everything runs in Docker containers on this VM. All commands are executed
from the project directory `/home/ipetrichenko/mirea-ai/petri-net-web` with
`sudo docker compose ...` (Docker group not set for the user, D-017).

| Service | Image | Notes |
| ------- | ----- | ----- |
| `app`   | built from `backend/Dockerfile` on `python:3.12-slim` | host port 8080 (default `APP_PORT`) → container port 8000; healthcheck GETs `/healthz`; SQLite on `petri-data` volume at `/data/sessions.db` (D-015, D-016) |
| `e2e`   | built from `e2e/Dockerfile` (Playwright Python + headless Chromium, tag pinned v1.49.1-jammy) | `BASE_URL=http://app:8000`; `depends_on: app (service_healthy)`; `./e2e` mounted at `/e2e`, `./docs/acceptance` mounted at `/e2e/screenshots`; default command `python -m pytest -v` |

Canonical commands (also the only ones quoted in the TEST_REPORT):

| Gate | Command |
| ---- | ------- |
| Build images | `sudo docker compose build` |
| Start app (for e2e / manual check) | `sudo docker compose up -d app` |
| Unit + property suite | `sudo docker compose run --rm app pytest` |
| Lint (ruff) | `sudo docker compose run --rm app ruff check src tests` |
| Types (mypy strict) | `sudo docker compose run --rm app mypy` (strict = true in `backend/pyproject.toml`) |
| E2E suite | `sudo docker compose run --rm e2e` (requires the app service healthy) |

No package is installed on the host; Python, pytest, hypothesis, ruff, mypy,
and Playwright/Chromium all live inside the containers (NFR-005).

## 3. Test matrix

| Layer | Technique | Tool | Location | What it covers |
| ----- | --------- | ---- | -------- | -------------- |
| unit | Deterministic tests, frozen fixtures | pytest | `backend/tests/test_core.py` | Semantics: ordered P/T, I/O weight-0 defaults, enablement, firing `µ' = µ − I(t) + O(t)`, marking order (A-06), D-014 anchors (all enabled at µ0; t1 → (5,5,2,5,4,3)) |
| unit | Parsing, valid + invalid inputs | pytest | `backend/tests/test_parser_text.py`, `backend/tests/test_parser_json_form.py` | All 3 channels (text / JSON / form): smoke fixture → exact S (FR-001…FR-003), repetition-as-weight, schema validation (unique names, positive weights, marking covers all places), malformed input → typed readable error, no net created |
| unit | Graph / KM construction | pytest | `backend/tests/test_reachability.py` | Reachability: node set = reachable markings, edge set = legal firings, µ0 root, 1503/4983 (D-009), cap abort (413, D-020/D-034); Karp–Miller: counter → single ω node (D-034), bounded net never gets ω, ω only in coverability kind |
| unit | Property reporting | pytest | `backend/tests/test_properties.py` | Frozen reports: smoke (D-009…D-013, D-035), counter (5.6), mutex (3/4, L4, safe, home), cyclic-50 (5.4), L0/L1 mix (t3 L0, t1/t2 L4, net L0), deadlocks in D-022 lexicographic order |
| unit | API endpoints | pytest + FastAPI TestClient | `backend/tests/test_api.py` | Every route: parse/graph/properties/fire/undo/reset/goto/queries/exports/sessions; report contract fields; typed errors (409 fire at deadlock, 413 cap, 422 validation, 404 deleted session); CSV/JSON export contents |
| property | Randomized invariant checking | hypothesis (inside the unit files above) | `test_core.py`, `test_reachability.py`, `test_properties.py`, `test_parser_text.py` | Firing balance (token conservation vs I/O weights), enabled consistency (report vs re-evaluation), graph edges legal + all nodes reachable from µ0, report determinism (same net → same report twice), safe ⇒ bounded, L4 ⇒ deadlock-free, computed level never exactly L2 (D-031), deadlocks ⇔ nodes with no active transition, parser text round-trip (canonical text of S re-parses to S) |
| e2e | Browser end-to-end | Playwright (Python), headless Chromium | `e2e/test_e2e.py` (run in the `e2e` container) | Scenarios E2E-1…E2E-5 (Section 5): text/JSON intake, graph + properties rendering, stepping/undo/reset, CSV/JSON downloads, session history restore; acceptance + failure screenshots |

## 4. Frozen acceptance fixtures

Expected values are frozen in `docs/REQUIREMENTS.md` §5 and
`docs/DECISIONS_LOG.md`; they are the acceptance baseline — any deviation is
a defect (REQUIREMENTS §5.3).

| Fixture | Source | Frozen expectations |
| ------- | ------ | ------------------- |
| Smoke net (raw text / JSON, the mandatory fixture) | REQUIREMENTS 5.1–5.3, 5.5; D-009…D-014, D-035 | 1503 markings / 4983 edges; per-place maxima [10, 8, 16, 29, 8, 10], global k = 29, bounded = true; safe = false; exactly 23 deadlocks (list in 5.5, D-022 order), not deadlock-free; all five transitions occur, none dead; per-transition levels all L1 (DAG via potential W, D-035) → net level L1; home state = false; at µ0 all t1..t5 enabled, firing t1 → (5, 5, 2, 5, 4, 3) |
| 50-node cyclic net (25 places + 25 transitions, token cycles) | REQUIREMENTS 5.4 | 25 markings / 25 edges; per-place maxima all 1 → safe (1-bounded); no deadlocks; no dead transitions; all 25 transitions L4 → net level L4; home state = true |
| Unbounded counter (P={p1}, T={t1}, I(t1)={} , O(t1)={p1:1}, µ0=(1)) | REQUIREMENTS 5.6; D-034 | Karp–Miller tree = single ω node (cap never hit); coverability report: p1 unbounded, approximation "omega", bounded/safe = false; t1 occurs and is L4 → net L4; no deadlocks (deadlock-free = true); home state = false |
| L0/L1-mix net (ADR-0004 example 4) | `test_properties.py::test_l0_live_mix` | t3 is L0 (dead, dead_transitions = ["t3"]), t1 and t2 are L4; net level = L0 (minimum over transitions); no deadlocks |
| Mutex net (classic mutual exclusion, 2 contenders + resource) | `test_reachability.py::mutex_net` | 3 markings / 4 edges; 1-bounded → safe; all transitions L4 → net L4; deadlock-free; home state = true; coverability tree has no ω |

The smoke net is the anchor fixture for the whole document (parse fixture,
E2E numbers, NFR-001 timing, CSV/JSON export contents).

## 5. E2E scenarios (Playwright, `e2e/test_e2e.py`)

All scenarios run against `http://app:8000` inside the `e2e` container.
UI text is Russian (NFR-006); wait strategy: polling on the target DOM state
with generous timeouts (no fixed sleeps, Section 7).

### E2E-1 — text intake + full analysis (acceptance screenshot)

1. Open `/`. The raw-text tab is pre-filled with the smoke net text (REQUIREMENTS 5.1).
2. Click «Проанализировать».
3. Wait until `#graph-stats` shows "узлов: 1503, рёбер: 4983" (D-009).
4. Assert `#canvas-graph` contains exactly 1503 nodes (count Cy nodes via `page.evaluate`).
5. Assert `#canvas-net` contains exactly 11 nodes: 6 places + 5 transitions (FR-015).
6. Assert the properties panel shows: global k = 29; «Безопасна» = нет;
   liveness level L1 (D-035); deadlocks count 23 (D-011).
7. Save the acceptance screenshot to `docs/acceptance/e2e-1-analysis.png`.

### E2E-2 — stepping (step / undo / reset)

1. Fresh page; parse the smoke text (same as E2E-1 steps 2–3).
2. At µ0 the place labels read "p1 (7)" / "p2 (4)". Click the transition
   button t1, then «Шаг» (FR-017; D-014).
3. Assert the net canvas labels now read "p1 (5)" and "p2 (5)"
   (marking (5, 5, 2, 5, 4, 3)); the history list contains the t1 step.
4. Click «Отмена» (undo): assert labels back to "p1 (7)" / "p2 (4)".
5. Click «Сброс» (reset): assert the history list is empty and p1 shows (7)
   again (FR-017 c3).

### E2E-3 — exports (CSV + JSON report)

1. Fresh page; parse the smoke text and wait for the graph (as E2E-1).
2. Click «CSV маркировок»; wait for the download and read the file:
   - header line is exactly `p1,p2,p3,p4,p5,p6` (declared P order);
   - total lines = 1504 (1 header + 1503 data rows, D-009);
   - second line is exactly `7,4,2,5,4,3` (µ0 row).
3. Click «JSON отчёта»; wait for the download; parse as JSON:
   - `global_k` = 29 (D-010);
   - `liveness.level` = "L1" (D-012/D-035);
   - `deadlocks` has exactly 23 entries (D-011).

### E2E-4 — JSON intake

1. Fresh page; switch to the JSON tab; paste the smoke JSON
   (REQUIREMENTS 5.2); click «Проанализировать».
2. Wait for the graph; assert the same frozen numbers as E2E-1:
   `#graph-stats` = 1503/4983, global k = 29, deadlocks 23, level L1
   (FR-002 c1: same S as text intake).

### E2E-5 — session history restore

1. Fresh page; parse the smoke text (as E2E-1).
2. Open «История сессий»: the just-created session is listed (≥ 1 item;
   FR-022).
3. Click the session; assert the analysis view is restored WITHOUT
   re-entering anything: `#graph-stats` shows 1503 nodes again and the
   properties panel shows k = 29 (FR-022 c2 — no recomputation from
   scratch; the stored structure is reused, D-023/ADR-0005).

### Failure handling

A pytest hook in `e2e/conftest.py` takes a screenshot into
`docs/acceptance/failures/` (mounted from the host) on every test failure,
so each red item in the TEST_REPORT has a reproducible artifact.

## 6. Entry / exit criteria

Entry (all must hold before the test run starts):

1. `sudo docker compose build` succeeds (both `app` and `e2e` images build).
2. `sudo docker compose up -d app` brings the app to healthy:
   `GET /healthz` returns 200 (compose healthcheck passes).

Exit (the run is finished and a verdict is issued):

1. Unit + property suite, ruff, mypy strict, and e2e are all green;
   pass/fail counts and durations are recorded in `docs/TEST_REPORT.md`.
2. Any red item is reproduced with the exact command (Section 2) and
   reported with steps + expected/actual; the verdict (accept / reject with
   blockers) is explicit.
3. Artifacts in place: `docs/acceptance/e2e-1-analysis.png` and, per
   failure, a screenshot in `docs/acceptance/failures/`.

## 7. Risks

| Risk | Impact | Mitigation |
| ---- | ------ | ---------- |
| Rendering 1503 nodes in `#canvas-graph` may be slow in headless Chromium | Flaky e2e waits, false failures | Poll on the real DOM condition (`#graph-stats` text, node count) with generous timeouts — never fixed sleeps; assertions read state, not timing |
| Playwright image version drift | Browser/Playwright mismatch breaks the e2e container | Image tag pinned (`mcr.microsoft.com/playwright/python:v1.49.1-jammy`); rebuild only via the pinned `e2e/Dockerfile` |
| No real user-load testing | NFR-001 (10 s budget) not verified under concurrency | Accepted: NFR-001 is a single-run budget, verified by timing the `/graph` call inside the container (recorded in TEST_REPORT); load testing is explicitly out of scope (Section 1) |
| SQLite on a named volume accumulates sessions between runs | E2E-5 "≥ 1 item" assertions affected by stale sessions | Assertions are written tolerance-based (≥ 1, "the newest"), not exact list equality |
| Large deterministic e2e page state (graph JSON) slows every scenario | Suite duration grows | Each scenario uses a fresh page; the heavy analysis is performed once per scenario, and the cap (50000) keeps the smoke build at 1503 nodes |
