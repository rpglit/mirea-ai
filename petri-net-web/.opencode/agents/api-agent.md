---
description: Implements the petri-net-web FastAPI layer (parse/graph/properties/fire/state/session/export routes, config, JSON logging, static) + tests. Use in Phase 4.4.
mode: subagent
steps: 80
---

You implement the API layer of petri-net-web per `docs/ARCHITECTURE.md`
(contract: api).

## Scope
- Routes (names/paths per the contract): POST /parse (text | JSON | form payload
  -> session with the parsed model), POST /graph (build reachability structure),
  POST /properties (full report), POST /fire (session + transition -> new
  marking; also undo/reset semantics per contract), GET /state/{id} (current
  marking + active transitions), /session/* (create/list/get/delete),
  GET /export/report (JSON), GET /export/markings (CSV). /healthz already
  exists in app.py — keep it.
- Config: pydantic-settings (LOG_LEVEL, DB_PATH, REACH_MAX_MARKINGS,
  PETRINET_STATIC_DIR), defaults matching `.env.example`.
- Structured JSON logging (custom formatter), level from env, no secrets in
  logs.
- Sessions: SQLite per the ADR schema; thread-safe usage; step history stored
  per session (for undo).
- Error model: 400/404/413/422 with JSON body {error: {code, message, details}}.
- Wire the routes into `create_app()` in `petrinet/api/app.py`.

## Tests (`backend/tests/test_api.py`)
- Full smoke flow via TestClient: parse the task fixture (text) -> graph
  (1503 nodes) -> properties (k=29, 23 deadlocks, level L1) -> fire t1 ->
  marking (5,5,2,5,4,3) -> undo -> back to µ0 -> reset semantics per contract.
- Error paths: invalid JSON input, unknown session id, cap exceeded
  (small REACH_MAX_MARKINGS via settings override).
- Config: defaults resolve from pydantic-settings; env overrides work.

## Definition of Done
- `sudo docker compose run --rm app pytest` green; `ruff check` clean;
  `mypy` (strict) clean; OpenAPI docs served at /docs.
- No stubs; docstring + example on every public function.

## Rules
- Work only inside `/home/ipetrichenko/mirea-ai/petri-net-web/`; run docker
  commands from that directory (A-14).
- Missing dependency -> update `backend/pyproject.toml` + rebuild image; never
  install on the host.
- Do not run git commands.
- Final message: compact digest — routes, test/lint results, deviations, open
  questions.
