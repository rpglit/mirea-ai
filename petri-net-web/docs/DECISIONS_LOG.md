# Decisions Log

Chronological log of all project decisions. Format: `D-NNN` (date) decision — rationale.

## Phase 0 (user answers, 2026-10-02)

- **D-001** UI language: Russian. Documentation: English (user: "как тебе лучше").
- **D-002** Project folder: `petri-net-web/` inside the repo root (user approved the name).
- **D-003** No external reference answer for the smoke net ("нет, если надо в инете найди").
  Web research: found MSU course material with the same p1..p6/t1..t5 net family and
  matching definitions (boundedness, safety, live transition) —
  `https://mk.cs.msu.ru/images/a/a5/MMSC_VP_03.pdf` (Блок 3), but no published answer
  for this exact fixture. Ground truth therefore derived in-house (see D-009..D-014).
- **D-004** Backend: FastAPI (Python 3.12) — "как будет быстрее".
- **D-005** Frontend: vanilla JS + CDN libraries — "как будет быстрее".
- **D-006** Graph visualization: Cytoscape.js — "как будет быстрее".
- **D-007** Sub-agent escalation limit: 3 dispatches before the orchestrator escalates
  to the user.
- **D-008** Git: `petri-net-web/` lives by its own rules (user: "для подпапки свои
  правила"); commits go to `main`; no push without an explicit command; the root
  README and other root files remain under the old repo policy.

## Ground truth for the smoke net (frozen acceptance baseline)

Computed 2026-10-02 by two independent stdlib implementations
(`/tmp/opencode/petri_ground_truth.py`, `/tmp/opencode/petri_liveness.py`:
BFS with dict-based firing vs DFS with incidence-vector firing; the reachability
sets and edge counts agree exactly).

- **D-009** Reachability graph: **1503 markings, 4983 edges** from µ0=(7,4,2,5,4,3).
- **D-010** Boundedness: per-place maxima p1..p6 = **[10, 8, 16, 29, 8, 10]**;
  global k = **29** (net is bounded, NOT safe).
- **D-011** Deadlocks: **23** (full list below); the net is **not** deadlock-free.
- **D-012** Transitions: all five occur (enabled somewhere). Under the strong
  liveness definition (MSU: for every reachable M there is K with M->*K and t
  enabled at K) **no transition is live** — a consequence of the reachable
  deadlocks. Liveness level (A-05 partition): **L1**.
- **D-013** Home state / reversibility: **False** — µ0 is not reachable from every
  reachable marking.
- **D-014** At µ0 all transitions t1..t5 are enabled; firing t1 at µ0 gives
  (5,5,2,5,4,3). (Anchors used by core/api tests.)

Deadlock list (p1..p6 order):
(1,0,11,18,1,0) (0,0,4,12,0,6) (0,0,12,6,0,2) (0,0,16,3,0,0) (0,0,3,7,1,7)
(0,0,1,5,0,9) (0,0,5,2,0,7) (0,0,5,24,1,3) (0,0,7,4,1,5) (1,0,13,13,0,0)
(0,0,6,14,1,4) (0,0,14,8,1,0) (0,0,10,11,1,2) (0,0,11,1,1,3) (0,0,6,29,0,2)
(0,0,2,17,1,6) (0,0,7,19,0,3) (0,0,10,26,0,0) (0,0,0,0,1,10) (0,0,3,22,0,5)
(0,0,11,16,0,1) (0,0,9,21,1,1) (0,0,8,9,0,4)

## Phase 1 (bootstrap, 2026-10-02)

- **D-015** Single container: FastAPI serves the JSON API and the static frontend
  (Cytoscape.js via CDN in the browser). Compose service `app`, container port 8000,
  host port **8080** (port 80 is Jupyter Lab on this VM).
- **D-016** Session storage: SQLite (stdlib `sqlite3`) on named volume `petri-data`
  at `/data/sessions.db` — persistence across restarts at near-zero cost.
- **D-017** Docker was absent on the VM; installed via apt (`docker.io` 29.1.3 +
  compose plugin 2.40.3, Ubuntu 24.04). Host is used for Docker only; all
  dev/run/test commands run inside containers (A-14). Docker group not set for the
  current user -> `sudo docker compose ...`.
- **D-018** Quality gates per phase: pytest (unit + hypothesis), ruff, mypy --strict,
  all executed inside the `app` container.
- **D-019** Sub-agent definitions live in `.opencode/agents/*.md` (opencode native
  markdown agents, mode: subagent; the reviewer is read-only via `permission.edit: deny`).
- **D-020** Reachability safety cap `REACH_MAX_MARKINGS` (default 50000) as a typed
  API error (A-15); Karp–Miller mode remains available for unbounded nets.
- **D-021** `frontend/index.html` is a bootstrap placeholder, replaced in Phase 4.5
  (A-16). No PNG endpoint server-side: PNG export is client-side (A-11).
