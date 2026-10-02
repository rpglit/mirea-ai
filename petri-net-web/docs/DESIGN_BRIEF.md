# Design Brief (fixed decisions for the architecture phase)

This brief pins the key decisions; the ADRs and ARCHITECTURE.md expand them into
full form. If you find a real flaw in a pinned decision, fix it in the ADR and
flag it in the final message.

## 1. Internal data model (immutable)
- `Marking` = `tuple[int, ...]` aligned with the declared place order
  (hashable, deterministic, O(|P|) firing).
- `PetriNet`: `places: tuple[str, ...]`, `transitions: tuple[str, ...]`,
  `inputs: tuple[tuple[tuple[str, int], ...], ...]` (per transition:
  (place, weight) pairs), `outputs` likewise, `initial_marking: Marking`.
  (Any equivalent immutable representation is fine if it preserves: hashable
  markings, declared order, positive integer weights, O(|P|) firing.)
- Semantics: t enabled at m iff m[p] >= w for every (p, w) in inputs(t);
  fire: m' = m - I(t) + O(t).

## 2. Reachability vs Karp–Miller
- API mode: `auto` (default) | `bounded` | `coverability`.
- `auto`/`bounded`: BFS reachability graph, hard cap `REACH_MAX_MARKINGS`;
  cap hit -> typed `CapExceededError` (HTTP 413), response suggests
  `coverability`.
- `coverability`: classical Karp–Miller tree with ω; expansion with the
  standard ancestor-correction step (componentwise max, ω where new > ancestor);
  ω dominates naturals. Termination: each correction strictly increases the
  number of ω's.
- Node identity: discovery-order index + marking tuple; edge id:
  `n<src>:t<n_dst>`.
- Properties on the tree use ω-semantics with a documented approximation caveat.

## 3. JSON input schema
- `docs/schemas/petri-net.schema.json`, JSON Schema 2020-12.
- Top level: `places` (array of unique names), `transitions` (unique),
  `inputs` / `outputs` (object: transition -> object: place -> integer weight
  >= 1), `initial_marking` (object: place -> integer >= 0, covers ALL places).
- Names: non-empty, pattern `^[A-Za-z_][A-Za-z0-9_]*$`.
- Absent top-level `inputs`/`outputs` = empty maps; absent per-transition entry
  = empty map (REQUIREMENTS §8.8).
- Raw text and form intake normalize to this JSON, then share one validator.
- Validation errors -> 422 with `{error: {code: "validation_failed", message,
  details: [{path, message}]}}`.

## 4. Liveness (final)
- "occurs": enabled at some reachable marking.
- "live" (strong, MSU): for every reachable M there is K with M ->* K and t
  enabled at K; algorithm = backwards closure from markings where t is enabled.
- Level partition: L4 all live; L3 all occur, not all live; L2 >= 1 live and
  >= 1 does not occur; L1 >= 1 occurs, none live; L0 none occur.
- Smoke net = L1 (D-012). Loop net (1 place, 1 self-loop transition, µ0=1) = L4.

## 5. Session storage (SQLite, stdlib sqlite3)
- File at `DB_PATH` (default `/data/sessions.db`, volume `petri-data`).
- One table `sessions`: `id TEXT PK (uuid4 hex)`, `name TEXT`,
  `created_at TEXT (ISO8601)`, `input_format TEXT`, `model_json TEXT`,
  `graph_json TEXT NULL`, `report_json TEXT NULL`, `current_marking TEXT`,
  `history_json TEXT`.
- Rationale: store parsed model + graph + report as JSON columns (smoke graph
  ~300 KB; recompute is wasteful); single-process access + `RLock` +
  `check_same_thread=False`.
- History: list of `{transition, from, to}`; undo pops last, reset restores µ0
  and clears history (FR-017).
- Delete: row removed; subsequent state request -> typed 404 (FR-022 c4).

## 6. Errors
- Hierarchy in `petrinet/errors.py`: `PetriNetError` base; `ParseError`
  (position + message); `ValidationError` (list of {path, message});
  `UnknownSessionError`; `CapExceededError`; `TransitionNotEnabledError`.
- Mapping: Parse/Validation -> 422; UnknownSession -> 404; CapExceeded -> 413;
  TransitionNotEnabled -> 409; else 500.
- Body: `{error: {code, message, details?}}`.
- Errors logged as structured JSON (session id, code, duration; user input
  echoed at most 200-char prefix).

## 7. API route table (paths fixed; request/response shapes in ARCHITECTURE.md)
- `POST /parse` {format: "text"|"json"|"form", payload} -> 201 {session_id, model summary}
- `POST /graph` {session_id, mode?: "auto"|"bounded"|"coverability"} -> {structure, stats}
- `POST /properties` {session_id, queries?: {reachable_marking?, coverable_marking?}} -> full report (+ query answers)
- `POST /fire` {session_id, action: "fire"|"undo"|"reset", transition?} -> {current_marking, active_transitions, history_tail}
- `POST /goto` {session_id, marking} -> {current_marking, active_transitions, history_tail} (marking must be a node of the stored graph)
- `GET /state/{session_id}` -> {current_marking, active_transitions, history}
- `GET /sessions` -> list; `GET /sessions/{id}` -> summary; `DELETE /sessions/{id}` -> 204
- `GET /sessions/{id}/export/report` -> JSON report; `GET /sessions/{id}/export/markings` -> CSV
- `GET /healthz` (exists)
- CSV format: header = place names in declared order, one row per reachable
  marking, rows in discovery (BFS) order, deterministic.
- All JSON responses deterministic key order (sorted).

## 8. UI contract
- Screens: input tabs (text/json/form) -> analysis view (net canvas + reachability
  canvas + properties panel + step panel) -> session history.
- API calls: tab submit -> POST /parse then POST /graph then POST /properties
  (sequential, progress states); click on a reachability-graph node switches
  the current marking via `POST /goto` {session_id, marking}, which validates
  that the marking is in the stored graph and sets it as current (recorded as a
  goto step in history). Step/Undo/Reset -> POST /fire with action
  fire/undo/reset. Exports: PNG client-side (Cytoscape), JSON/CSV
  via the export endpoints (browser download).
- Cytoscape shapes: net canvas nodes {id, data:{kind: "place"|"transition",
  label, tokens?}}, edges {data:{weight, source, target}}; graph canvas nodes
  {id, data:{marking, deadlock?}}, edges {data:{transition}}.
