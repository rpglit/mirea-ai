# Assumptions

Fixed during Phases 0–1. Any item may be overridden by the user at any time;
overrides are recorded in `DECISIONS_LOG.md`.

- **A-01** UI language: Russian. Documentation: English.
- **A-02** The smoke net (task fixture) has no externally published reference
  answer. Ground truth is derived in-house: two independent stdlib implementations
  (BFS with dict-based firing; DFS with incidence-vector firing) agree on the
  reachability   set. Frozen numbers: `DECISIONS_LOG.md` D-009..D-014.
- **A-03** Boundedness: place `p` is `k`-bounded iff `µ(p) <= k` for every
  reachable marking; the net is bounded iff all places are (global `k` =
  `max_p`). Unboundedness is detected via `ω`-tokens in the Karp–Miller
  coverability tree.
- **A-04** Safety: the net is safe iff it is 1-bounded.
- **A-05** Liveness: the classical per-transition scale L0–L4 (Murata;
  confirmed against Wikipedia "Petri net", Liveness section; corrected per
  D-031 — the earlier operational partition is void). Per transition:
  - L0 dead — never enabled at any reachable marking;
  - L1 potentially fireable — enabled at some reachable marking (occurs);
  - L2 — fires arbitrarily often (some sequence fires it >= k times, for
    every k);
  - L3 — fires infinitely often in some infinite sequence;
  - L4 live — from every reachable marking a firing sequence reaches a
    marking where it is enabled (MSU strong definition).
  On a finite reachability graph L2 <=> L3 (a reachable cycle containing a
  t-edge), so a computed level is never exactly L2. Net level = the minimum
  over all transitions ("the net is Lk-live iff all transitions are");
  L4-ness of the net implies deadlock-free. For unbounded nets the level is
  reported on the coverability tree with the documented ω-approximation
  caveat.
- **A-06** Marking order = declared order of `P` (task fixture: p1..p6).
- **A-07** Raw text notation grammar is fixed by the parser per the architecture
  contract; the task fixture is the mandatory parse fixture.
- **A-08** JSON input schema is authoritative from the task
  (`places`, `transitions`, `inputs`, `outputs`, `initial_marking`); the
  architecture adds constraints (unique names, positive integer weights,
  marking covers all places).
- **A-09** Session storage: SQLite (stdlib `sqlite3`) at `$DB_PATH`
  (default `/data/sessions.db`, named volume `petri-data`).
- **A-10** Host port 8080 (port 80 is taken by Jupyter Lab on this VM).
- **A-11** Graph PNG export is client-side (Cytoscape.js
  `export({type: "png"})`); server-side `/export` provides the JSON report and
  the CSV of markings.
- **A-12** Karp–Miller construction follows the standard coverability semantics
  (`m ≼ m'`, `ω` dominates any natural number), per the architecture ADR.
- **A-13** Escalation limit: max 3 dispatches of the same sub-agent task before
  the orchestrator escalates to the user (Phase 0 answer).
- **A-14** All development and execution happens inside Docker containers. The
  host runs Docker only (installed in Phase 1 — it was absent from the VM).
  Docker commands: `sudo docker compose ...` (user not in the docker group).
- **A-15** Reachability construction has a safety cap `REACH_MAX_MARKINGS`
  (default 50000); exceeding it is a typed API error and the UI offers the
  Karp–Miller (coverability) mode.
- **A-16** `frontend/index.html` is a Phase-1 placeholder; it is fully replaced
  in Phase 4.5 (ui-agent).
