# Petri Net Web

A web application for working with Petri nets: description intake in three formats
(raw text notation, JSON, interactive form), reachability graph construction
(Karp–Miller coverability tree for unbounded nets), property analysis, interactive
step execution, exports, and session history. Plus a «Задание из практикума»
screen: a catalog of 71 methodic tasks (40 Petri nets / 23 linear systems / 8
finite automata) with built-in data, one-click solving, and «Дано/Найти/Решение/
Ответ» reports in the methodic format (Petri net canvases, automaton graphs with
word processing by ticks, formulas and tables for LSS).

**UI language:** Russian. **Documentation:** English.

## Quick start

```bash
docker compose up --build
# open http://localhost:8080
```

The single `app` container (Python 3.12) serves both the JSON API and the static
frontend. Session history is stored in SQLite on the named volume `petri-data`.

## What it does

- **Intake** — raw mathematical notation (the task's fixture is pre-filled in the
  text tab), JSON per `docs/schemas/petri-net.schema.json`, or the interactive
  form (input/output/inhibitor arcs, priorities, delays, session name).
- **Task solver** — «Задание из практикума» screen: catalog of 71 methodic tasks
  with pre-filled data, `POST /solve` (stateless, methodic report), Petri net
  saving into a named session, automaton graph with tick-by-tick word processing,
  PNG export of every canvas.
- **Reachability** — full reachability graph for bounded nets (safety cap
  `REACH_MAX_MARKINGS`, typed 413 on overflow) or the Karp–Miller coverability
  tree with ω-tokens for unbounded nets.
- **Properties** — per-place and global boundedness (k), safety, classical
  liveness scale L0–L4 (per transition and net level), marking reachability and
  coverability queries, deadlocks, dead transitions, home state / reversibility,
  deadlock-free.
- **Playback** — enabled transitions (green on the canvas, one click fires it),
  «Срабатывание / Отмена / Сброс», clickable step history, click a marking or an
  edge on the reachability graph to switch to it, the current node is
  highlighted and follows the playhead.
- **Exports** — PNG of the active canvas and «PNG of all» (client-side,
  blob-promise), JSON report and CSV of all reachable markings (server-side).
- **Sessions** — stored in SQLite, named by the user, listed (limit 50, newest
  first) / restored / deleted from the UI; all backend error messages in
  Russian.

## Reference example (smoke net)

For the pre-filled fixture (P = p1..p6, T = t1..t5, µ0 = (7,4,2,5,4,3)) the app
produces, verified by the e2e suite and an independent implementation:

- 1503 reachable markings, 4983 firing edges;
- per-place bounds p1≤10, p2≤8, p3≤16, p4≤29, p5≤8, p6≤10, global k = 29,
  bounded but not safe;
- liveness level **L1** (all five transitions occur; none lies on a reachable
  cycle — the reachability graph is a DAG);
- 23 deadlocks, no dead transitions, home state = false, not deadlock-free.

## Configuration

All settings have defaults (see `.env.example`). Copy it to `.env` to override:

| Variable             | Default             | Meaning                                        |
| -------------------- | ------------------- | ---------------------------------------------- |
| `APP_PORT`           | `8080`              | Host port for the app                          |
| `LOG_LEVEL`          | `INFO`              | Structured JSON log level                      |
| `DB_PATH`            | `/data/sessions.db` | SQLite sessions file (`petri-data` volume)     |
| `REACH_MAX_MARKINGS` | `50000`             | Safety cap for reachability construction       |
| `PETRINET_STATIC_DIR`| `/app/static`       | Static frontend directory (in-container path)  |

## Layout

```
backend/     FastAPI app (src layout: src/petrinet), Dockerfile (node build
             stage for the frontend + Python runtime), pyproject.toml
frontend/    Vue 3 (Composition API) + Vite + Cytoscape.js (npm); the build
             output (dist/) is served by the API as static files
e2e/         Playwright end-to-end tests (own container, headless chromium)
docs/        requirements, architecture, ADRs, test plan/report, decisions log,
             JSON schema, acceptance artifacts (reports, CSV, screenshots)
.opencode/   agent definitions for the development workflow
```

## Checks (all inside containers, run from this directory)

```bash
# unit + property tests (263)
sudo docker compose run --rm app pytest

# linter / type checker
sudo docker compose run --rm app ruff check src tests
sudo docker compose run --rm app mypy

# end-to-end suite (8 scenarios, headless chromium against the app service;
# the suite also asserts a clean console — 0 errors and 0 warnings)
sudo docker compose run --rm e2e
```

## Documentation

- [Requirements](docs/REQUIREMENTS.md) — FR/NFR with acceptance criteria
- [Architecture](docs/ARCHITECTURE.md) — components, module contracts, API, UI
- [ADR/](docs/ADR/) — key design decisions
- [Decisions log](docs/DECISIONS_LOG.md) — chronological history of all decisions
- [Assumptions](docs/ASSUMPTIONS.md) — fixed interpretations
- [Test plan](docs/TEST_PLAN.md) / [Test report](docs/TEST_REPORT.md)
- [Acceptance artifacts](docs/acceptance/) — report, markings CSV, screenshots
