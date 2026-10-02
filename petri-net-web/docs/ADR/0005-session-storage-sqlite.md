# ADR-0005: Session storage (SQLite)

Status: Accepted (2026-10-02)

**Context**

FR-022 requires each analyzed net plus its results to be stored, listed,
and reopened — with visualization, reachability graph, properties panel
and exports restored without recomputation (c2) — and to persist across
container restarts (c3). The task allows in-memory or SQLite
(REQUIREMENTS §8.7); D-016 / A-09 pin SQLite at `$DB_PATH` (default
`/data/sessions.db`) on volume `petri-data`; brief §5 pins the table.
A session also holds expensive artifacts: the smoke reachability graph
is 1503 markings / 4983 edges, ~300 KB of JSON (D-009).

**Decision**

One SQLite database (stdlib `sqlite3`), one row per session:

```sql
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,  -- uuid4 hex
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL,     -- ISO 8601 UTC
    input_format    TEXT NOT NULL,     -- "text" | "json" | "form"
    model_json      TEXT NOT NULL,     -- parsed net (ADR-0001 shape)
    graph_json      TEXT,              -- reachability structure; NULL until /graph
    report_json     TEXT,              -- properties report; NULL until /properties
    current_marking TEXT NOT NULL,     -- JSON array of token counts, declared place order
    history_json    TEXT NOT NULL      -- JSON array of {transition, from, to}; initially "[]"
);
-- schema version, bumped by migrations:
PRAGMA user_version = 1;
```

Why SQLite over in-memory:

- **Persistence across restarts (FR-022 c3).** An in-memory dict dies
  with the process; the criterion demands surviving container
  restarts, so the store must be on disk — SQLite on the
  volume-mounted `$DB_PATH` gives that with no external service.
- **Stdlib, no extra dependency.** `sqlite3` ships with CPython 3.12:
  nothing to install, no DB server container, no pool, no new failure
  mode.
- **Reopen without recompute (FR-022 c2).** The ~300 KB smoke graph
  and report are stored, not derived; re-running the BFS (NFR-001
  budget: up to 10 s) on every reopen would be wasteful.

JSON columns rather than normalized tables: the model / graph / report
shapes are fixed by ADR-0001 and brief §2 and evolve with the code;
opaque JSON keeps the schema flat (one table, no joins), makes a
session one atomic row, and lets `graph_json` / `report_json` stay
NULL until the corresponding endpoint runs.

Concurrency: single uvicorn process (one worker); one `sqlite3`
connection with `check_same_thread=False`, all reads/writes under one
`RLock` — access is already serialized, so WAL is not needed.

History (FR-017): `history_json` is the ordered list of
`{transition, from, to}` steps (marking arrays). `undo` pops the last
entry and restores its `from`; `reset` sets `current_marking` back to
the model's initial marking µ0 and replaces the history with `[]`.

Deletion (FR-022 c4): `DELETE FROM sessions WHERE id = ?`, no
soft-delete. The session disappears from `GET /sessions`; any later
request against it (`GET /state/{id}`, `/fire`, exports) returns the
typed 404 error body (brief §6) and its step history is not
recoverable.

Ids: `id` = `uuid4().hex`, generated server-side at `POST /parse`.

**Consequences**

- No new image dependencies; the DB file is the only mutable state —
  a backup is a copy of `/data/sessions.db`.
- A parsed-but-never-analyzed session (NULL graph/report) reopens in
  its post-parse state; the UI re-runs `/graph` + `/properties` on
  demand instead of serving stale artifacts.
- Row size grows with the graph: a 50000-marking run (D-020) yields a
  multi-MB `graph_json`; fine for SQLite, one statement per update.
- Single process + one connection is a hard invariant: more uvicorn
  workers or a second client on the file would break
  `check_same_thread=False` safety; scaling out needs
  connection-per-thread + WAL and is out of scope.
- `user_version` is the migration path: checked at startup, fail fast
  on unknown versions.
- Deletion is hard; the deleted session's history is unrecoverable
  (accepted, FR-022 c4).
