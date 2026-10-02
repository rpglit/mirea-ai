# Requirements — petri-net-web

|            |                                                                 |
| ---------- | --------------------------------------------------------------- |
| Status     | v1.0 (Phase 2 deliverable, requirements-agent)                  |
| Date       | 2026-10-02                                                      |
| Sources    | Product-owner task statement (Appendix A); `README.md`; `.env.example`; `docs/DECISIONS_LOG.md`; `docs/ASSUMPTIONS.md` |
| Language   | Requirements in English (A-01); UI strings in Russian           |

## 1. Purpose and scope

petri-net-web is a single-container web application for working with Petri nets.
A user submits a net description in one of three formats (raw mathematical
text, JSON, interactive form); the app builds the internal representation
S = (P, T, I, O, µ0), constructs the reachability graph (or the Karp–Miller
coverability tree for unbounded nets), computes the full property set
(boundedness, safety, liveness L0–L4, marking reachability, coverability,
deadlocks, dead transitions, reversibility/home state, deadlock-free), and
provides an interactive UI: net visualization with tokens, reachability-graph
visualization with click-to-switch marking, step-by-step playback (step /
reset / undo + history), a properties panel, and exports (graph PNG, report
JSON, markings CSV). Session history is persisted.

Explicitly out of scope: link sharing (task item 7, NFR-009), dark theme
(task item 8, NFR-007), CI pipelines (NFR-008). See Section 7.

Requirement identifiers are stable: `FR-xxx` (functional), `NFR-xxx`
(non-functional). Each requirement lists a description, testable acceptance
criteria, and its source. The mandatory smoke net (task fixture) is an
acceptance fixture for the whole document (Section 5) with frozen expected
numbers from `DECISIONS_LOG.md`, ground-truth section D-009…D-014.

## 2. Glossary

| Term | Meaning in this project |
| ---- | ----------------------- |
| Petri net (S) | Tuple S = (P, T, I, O, µ0): finite sets of places P and transitions T (both in declared order), input map I, output map O, initial marking µ0. |
| Place | Node p ∈ P that holds tokens; rendered as a circle in the UI. |
| Transition | Node t ∈ T that can fire; rendered as a bar in the UI. |
| Arc | Directed connection p → t (weight I(t)(p)) or t → p (weight O(t)(p)). Repetition of a place in I(t)/O(t) in raw text means arc weight (T9). |
| Arc weight | Positive integer number of tokens consumed/produced by the arc. |
| Marking | Vector µ over P in declared order; µ(p) = token count of place p. |
| Initial marking µ0 | Marking from which reachability is computed. |
| Enabled | t is enabled at µ iff µ(p) ≥ I(t)(p) for every p ∈ P. |
| Firing | Firing enabled t at µ gives µ' = µ − I(t) + O(t) (vector arithmetic over all places). |
| Reachability graph | Directed graph: nodes = all markings reachable from µ0; edge µ → µ' labeled by the transition t that fires. |
| Coverability | m is covered by m' iff m(p) ≤ m'(p) for all p. |
| Karp–Miller coverability tree | Finite tree over markings with ω tokens, built with subsumption; ω dominates any natural number (A-12). |
| ω token | Symbol meaning "arbitrarily many"; a place holding ω in the coverability tree makes the net unbounded (A-03). |
| k-bounded (place) | Place p is k-bounded iff µ(p) ≤ k for every reachable marking; its bound k_p = max over reachable markings (A-03). |
| Bounded (net) | Net is bounded iff every place is bounded; global k = max over p of k_p. |
| Safe | Net is 1-bounded (A-04). |
| Occurs (transition) | t occurs iff t is enabled at at least one reachable marking (A-05). |
| L0–L4 (transition) | Classical per-transition scale (A-05): L0 dead — never fires; L1 potentially fireable — fires in some firing sequence; L2 — fires arbitrarily often (in some sequence >= k times for every k); L3 — fires infinitely often in some infinite sequence; L4 live — from every reachable marking a firing sequence reaches an enabled marking (MSU strong definition). On a finite reachability graph L2 <=> L3 (a reachable cycle containing a t-edge), so a computed level is never exactly L2. |
| Liveness level L0–L4 (net) | The net is Lk-live iff ALL of its transitions are; the net level is the minimum over transitions. L4 implies deadlock-free. |
| Deadlock (dead marking) | Reachable marking at which no transition is enabled. |
| Dead transition | Transition that never occurs (not enabled at any reachable marking). |
| Home state | µ0 is the home state iff µ0 is reachable from every reachable marking. |
| Reversible | Net is reversible iff µ0 is the home state. |
| Deadlock-free | No reachable deadlock markings. |
| Session | One ingested net plus its computed analysis, stored in session history (FR-022). |

## 3. Functional requirements

### FR-001 — Intake: raw text (mathematical notation)

The application accepts a net description as plain text in the mathematical
notation of the task statement: set declarations of P and T, per-transition
input/output sets with repetition-as-weight, and the initial marking as an
ordered tuple. The exact grammar is fixed by the parser per the architecture
contract (A-07); the mandatory smoke-net text (Section 5.1) is the parse
fixture.

Acceptance criteria:

1. Given the smoke-net text (Section 5.1), the app yields S with
   P = [p1, p2, p3, p4, p5, p6] (declared order), T = [t1, t2, t3, t4, t5],
   I(t1) = {p1: 2}, O(t1) = {p2: 1}, I(t2) = {p1: 1, p6: 1}, O(t2) = {p3: 2},
   I(t3) = {p2: 1}, O(t3) = {p4: 3}, I(t4) = {p2: 1, p3: 1, p4: 2},
   O(t4) = {p5: 1, p6: 1}, I(t5) = {p5: 2}, O(t5) = {p1: 1, p3: 1},
   µ0 = (7, 4, 2, 5, 4, 3).
2. Repetition in I(t)/O(t) is counted as arc weight (I(t1) = {p1, p1} →
   weight 2); marking tuple positions follow the declared order of P (A-06).
3. Malformed text (a symbol in I/O not declared in P/T, non-integer marking
   value, marking length ≠ |P|) is rejected with a readable error naming the
   problem; no net is created.

Source: task item 1a, T9 (semantics); A-06, A-07.

### FR-002 — Intake: JSON

The application accepts a net as JSON following the task schema:
`places`, `transitions`, `inputs`, `outputs`, `initial_marking`
(Section 5.2, A-08).

Acceptance criteria:

1. Given the smoke-net JSON (Section 5.2), the app yields the same S as
   FR-001 criterion 1.
2. Validation (A-08): place and transition names must be unique; arc weights
   must be positive integers; `initial_marking` must cover all places (a
   missing place is a validation error).
3. Invalid JSON or schema violations are rejected with a structured error
   listing the problem(s); no net is created.
4. If a declared transition is absent from `inputs` or `outputs`, the
   behavior (empty I(t)/O(t) vs validation error) must be fixed by the
   architecture and applied consistently; whichever is chosen, it is
   documented and covered by a test.

Source: task item 1b, T9; A-08.

### FR-003 — Intake: interactive web form

The application provides a web form to build a net interactively: places,
transitions, weighted arcs (place → transition and transition → place), and
the initial marking per place.

Acceptance criteria:

1. The form allows adding/removing places and transitions with unique names,
   adding arcs with integer weight ≥ 1 in both directions (P→T and T→P), and
   setting each place's initial token count (integer ≥ 0).
2. Submitting a form filled to describe the smoke net (P p1..p6, T t1..t5,
   arcs and µ0 per Section 5) yields the same S as FR-001 criterion 1.
3. The form rejects (client-side and server-side) empty or duplicate names,
   arc weight < 1, and negative token counts, with a readable error.
4. A form with zero places or zero transitions cannot be submitted as a net.

Source: task item 1c.

### FR-004 — Internal representation S = (P, T, I, O, µ) and semantics

After successful intake, the net is held in the internal representation
S = (P, T, I, O, µ0) and all analysis/playback uses the task semantics (T9).

Acceptance criteria:

1. P and T are ordered sequences (declared order preserved); I and O map each
   transition to place → positive-integer weight (places absent from I(t) /
   O(t) have weight 0).
2. Enablement: t is enabled at µ iff µ(p) ≥ I(t)(p) for all p ∈ P. Firing:
   µ' = µ − I(t) + O(t) over all places.
3. Markings are compared, printed, and exported in declared order of P (A-06).
4. Fixture: for the smoke net, at µ0 all five transitions t1..t5 are enabled;
   firing t1 at µ0 gives (5, 5, 2, 5, 4, 3) (D-014).

Source: task item 2, T9; A-06.

### FR-005 — Reachability graph construction

The application constructs the full reachability graph of the current net:
every marking reachable from µ0 plus the firing edges between them.

Acceptance criteria:

1. Node set = exactly the markings reachable from µ0 (each marking once);
   edge set = all triples (µ, t, µ') where t is enabled at µ and
   µ' = µ − I(t) + O(t). µ0 is the root and is always included.
2. Fixture: for the smoke net the graph has exactly 1503 markings and 4983
   edges (D-009).
3. Construction respects the safety cap `REACH_MAX_MARKINGS` (NFR-002); the
   smoke net (1503 markings) completes at the default cap (50000).
4. For unbounded nets, exact construction may be infeasible; the app supports
   Karp–Miller mode (FR-006) and the UI can switch modes (A-15).

Source: task item 3 (reachability part), T9.

### FR-006 — Karp–Miller coverability tree (unbounded nets)

For unbounded nets (or on user request) the application builds the
Karp–Miller coverability tree with ω tokens using standard coverability
semantics (m covered by m' makes m' redundant; ω dominates any natural)
(A-12).

Acceptance criteria:

1. The tree terminates for the secondary fixture (Section 5.6, an unbounded
   net) and contains at least one ω token.
2. Unboundedness is detected via ω tokens: a place holding ω is reported
   unbounded (A-03).
3. Properties computed on the coverability tree (boundedness, liveness level,
   coverability queries) are presented with the documented ω-approximation
   caveat (A-05).
4. The user can select coverability mode for any net; the UI explicitly offers
   the switch after a `REACH_MAX_MARKINGS` abort (A-15, NFR-002).
5. The coverability build also honors `REACH_MAX_MARKINGS` as a safety cap
   (typed 413 error): the tree of a bounded net with a large state space can
   be exponentially larger than the reachability graph (D-034); for unbounded
   nets the tree is small (ω compression), so the cap never changes their
   result.

Source: task item 3 (Karp–Miller part); A-03, A-12, A-15, D-034.

### FR-007 — Boundedness (per place and global)

The application computes boundedness: per-place bounds and the global bound.

Acceptance criteria:

1. For each place p, report k_p = max µ(p) over reachable markings; if p
   holds ω in the coverability tree, report p as unbounded (A-03).
2. Report global k = max of k_p over p and the boolean "bounded" (all places
   bounded).
3. Fixture: for the smoke net, per-place maxima p1..p6 = [10, 8, 16, 29, 8,
   10], global k = 29, bounded = true (D-010).

Source: task item 4 (boundedness); A-03; D-010.

### FR-008 — Safety

The application determines whether the net is safe.

Acceptance criteria:

1. The net is safe iff it is 1-bounded, i.e., every k_p ≤ 1 (A-04).
2. Fixture: for the smoke net, safe = false (k_p3 = 16 > 1) (D-010).

Source: task item 4 (safety); A-04.

### FR-009 — Liveness (per transition and level L0–L4)

The application classifies each transition by the classical L0–L4 scale and
the net as a whole (net level = the minimum over transitions; "the net is
Lk-live iff all transitions are Lk-live"), per A-05.

Acceptance criteria:

1. Per transition t (on the finite reachability graph): L0 (dead) — never
   enabled at any reachable marking; L1 (potentially fireable) — enabled at
   some reachable marking; L2 — fires arbitrarily often: for every k there is
   a finite firing sequence firing t at least k times; L3 — fires infinitely
   often in some infinite firing sequence; L4 (live) — from every reachable
   marking there exists a firing sequence reaching a marking where t is
   enabled (MSU strong definition).
2. Computation on a finite reachability graph: L2 and L3 are decided by the
   same test — existence of a reachable cycle containing a t-edge (e.g. via
   strongly-connected components); L4 by the backwards closure from the
   markings where t is enabled. A computed per-transition level is therefore
   one of L0, L1, L3, L4 (never exactly L2); L1/L2/L3/L4 imply the previous
   ones.
3. Net level = the minimum per-transition level (order L0 < L1 < L2 < L3 <
   L4). A net at L4 is deadlock-free (the deadlock list is empty).
4. Fixture: for the smoke net all five transitions are L3 (each lies on a
   reachable cycle; none is L4 — the 23 reachable deadlocks break strong
   liveness), so the net level = L3 (D-012, corrected per D-031).
5. For unbounded nets the level is reported on the coverability tree with the
   ω-approximation caveat (A-05; FR-006 criterion 3).

Source: task item 4 (liveness); A-05; D-012; D-031.

### FR-010 — Reachability of specific markings

The user can query whether a specific marking is reachable from µ0.

Acceptance criteria:

1. Given a target marking entered in declared order of P, the app answers
   "reachable" / "not reachable" (membership in the reachability-graph node
   set; in coverability mode — with the ω-approximation caveat).
2. Fixture: for the smoke net — (7, 4, 2, 5, 4, 3) is reachable (it is µ0);
   (5, 5, 2, 5, 4, 3) is reachable (one step via t1, D-014); (11, 0, 0, 0, 0,
   0) is not reachable (exceeds the p1 maximum of 10, D-010).
3. A target marking with a value above some place's reachable maximum is
   answered "not reachable" without constructing a new graph.

Source: task item 4 (reachability of specific markings).

### FR-011 — Coverability

The user can query whether a marking is coverable; the app also reports
coverability-based unboundedness (FR-006).

Acceptance criteria:

1. Given a target marking M, the app answers whether some reachable marking
   m exists with m(p) ≥ M(p) for all p (m covers M); ω ≥ any natural
   (A-12 semantics).
2. Fixture: for the smoke net — M = (7, 4, 2, 5, 4, 3) is coverable;
   M = (0, 0, 0, 0, 0, 0) is coverable (µ0 covers it); M = (11, 0, 0, 0, 0, 0)
   is not coverable (p1 maximum = 10, D-010).
3. For unbounded nets, coverability answers are computed on the Karp–Miller
   tree with the ω-approximation caveat (FR-006 criterion 3).

Source: task item 4 (coverability); A-03, A-12.

### FR-012 — Deadlocks and dead transitions

The application detects deadlocks (dead reachable markings) and dead
transitions (transitions that never occur).

Acceptance criteria:

1. A deadlock is a reachable marking at which no transition is enabled; the
   app reports the full list and the count.
2. A dead transition is a transition that does not occur (FR-009 criterion
   1); the app reports the list (possibly empty).
3. Fixture: for the smoke net exactly 23 deadlocks (list in Section 5.5,
   D-011) and zero dead transitions (all five occur, D-012).

Source: task item 4 (deadlocks and dead transitions); D-011, D-012.

### FR-013 — Reversibility / home state

The application determines whether µ0 is the home state (net reversible).

Acceptance criteria:

1. The app answers "home state: yes/no": yes iff every reachable marking can
   reach µ0 (equivalently, the backwards reachability set of µ0 equals the
   whole reachability set).
2. Fixture: for the smoke net home state = no — µ0 is not reachable from
   every reachable marking (D-013).

Source: task item 4 (reversibility / home state); D-013.

### FR-014 — Deadlock-free

The application determines whether the net is deadlock-free.

Acceptance criteria:

1. The app answers "deadlock-free: yes/no": yes iff there are no reachable
   deadlock markings (FR-012 criterion 1).
2. Fixture: for the smoke net deadlock-free = no (23 deadlocks, D-011).

Source: task item 4 (deadlock-free).

### FR-015 — UI: net visualization

The UI renders the net: places, transitions, weighted arcs, and tokens.

Acceptance criteria:

1. Places render as labeled circles, transitions as labeled bars, arcs as
   directed edges; arcs with weight > 1 display the weight.
2. Token counts are shown on places for the current marking (initial marking,
   a marking selected in the reachability graph per FR-016, or the marking
   reached during playback per FR-017).
3. Fixture: the smoke net renders 6 places, 5 transitions, and 15 arcs:
   p1→t1 (2), t1→p2 (1); p1→t2 (1), p6→t2 (1), t2→p3 (2); p2→t3 (1),
   t3→p4 (3); p2→t4 (1), p3→t4 (1), p4→t4 (2), t4→p5 (1), t4→p6 (1);
   p5→t5 (2), t5→p1 (1), t5→p3 (1).
4. Fixture: the 50-node cyclic net (Section 5.4) renders all 25 places and 25 transitions as nodes, all 25 arcs with labels, every node is clickable, and token counts are visible in the DOM/canvas.

Source: task item 5 (visualization of the net).

### FR-016 — UI: reachability graph visualization with click-to-switch

The UI renders the reachability graph; clicking a node switches the net view
to that marking.

Acceptance criteria:

1. Nodes = reachable markings, labeled with the marking tuple in declared
   order of P; edges = firing steps, labeled by the transition.
2. Clicking a node sets the current marking: the net visualization (FR-015)
   updates its token counts to that marking, and the clicked node is
   highlighted as current.
3. The graph supports pan/zoom; from µ0 every reachable marking can be
   reached by following the drawn edges.
4. Performance: on the smoke-net reachability graph (1503 nodes), clicking any node switches the current marking in the net view within 2 s and pan/zoom stays interactive (no frozen UI); QA may assert the switched marking via the API state endpoint after the click.
5. In coverability mode the Karp–Miller tree (FR-006) renders in the same
   panel, with ω shown in place of a number.

Source: task item 5 (state-graph visualization, click → switch marking).

### FR-017 — UI: step-by-step playback (step / reset / undo, history)

The UI allows firing enabled transitions step by step from the current
marking, with step, reset, and undo controls and a step history.

Acceptance criteria:

1. The transitions enabled at the current marking (FR-004 criterion 2) are
   displayed as selectable; transitions not enabled at the current marking
   cannot be fired.
2. Selecting an enabled transition fires it: the current marking becomes
   µ − I(t) + O(t), the net and graph views update, and the step is appended
   to the history.
3. "Undo" reverts the last step (restores the previous marking); "Reset"
   returns the current marking to µ0 and clears the step history.
4. The step history lists, in order, each step's transition and resulting
   marking, and the user can inspect it.
5. Fixture: from the smoke-net µ0, t1..t5 are all selectable (D-014); firing
   t1 makes the current marking (5, 5, 2, 5, 4, 3) (D-014); Undo restores
   (7, 4, 2, 5, 4, 3); after any number of steps, Reset restores
   (7, 4, 2, 5, 4, 3) and an empty history.

Source: task item 5 (step-by-step playback).

### FR-018 — UI: properties panel

The UI shows the computed properties of the current net.

Acceptance criteria:

1. The panel displays: per-place bounds k_p and unbounded flags (FR-007),
   global k and "bounded" (FR-007), "safe" (FR-008), per-transition status
   (does not occur / occurs / live) and liveness level L0–L4 (FR-009),
   deadlock list and count (FR-012), dead transitions (FR-012), home state /
   reversibility (FR-013), deadlock-free (FR-014), graph statistics (marking
   and edge counts, FR-005).
2. For the smoke net the panel values match D-009…D-014 (Section 5.3).
3. In coverability mode the panel shows Karp–Miller-derived values with the
   ω-approximation caveat (FR-006 criterion 3).
4. Query results (FR-010, FR-011) are shown with the entered target marking
   and the answer.

Source: task item 5 (properties panel).

### FR-019 — Export: graph PNG

The user can export the currently displayed graph (reachability graph or
coverability tree) as a PNG image.

Acceptance criteria:

1. A user action downloads a PNG file of the current graph view (client-side
   rendering per A-11, D-021).
2. The downloaded file is a valid, non-blank PNG (correct magic bytes; image
   dimensions > 0) and contains the rendered nodes/edges.

Source: task item 5 (export PNG); A-11; D-021.

### FR-020 — Export: report JSON

The user can download a machine-readable JSON report of the full analysis.

Acceptance criteria:

1. The report contains: the net definition (P, T, I, O, µ0 in declared
   order), the analysis mode (reachability / coverability), graph statistics
   (marking and edge counts), and all computed properties: per-place bounds,
   global k, bounded, safe, per-transition liveness status, liveness level,
   deadlock list, dead transitions, home state, deadlock-free (FR-005…FR-014).
2. Fixture: for the smoke net the report contains 1503 markings / 4983 edges
   (D-009), per-place maxima [10, 8, 16, 29, 8, 10] and global k = 29
   (D-010), 23 deadlocks (D-011), per-transition levels all L3 and net
   liveness level L3 (D-012, D-031), home state = false (D-013), bounded =
   true and safe = false (D-010).
3. The report is valid JSON (parses) and is downloadable from the properties
   panel (server-provided per A-11).

Source: task item 5 (export report JSON); A-11.

### FR-021 — Export: markings CSV

The user can download the reachable markings as a CSV file.

Acceptance criteria:

1. The CSV header row = place names in declared order of P; each data row =
   one reachable marking with values in that order (one row per node of the
   reachability graph, no duplicates).
2. Fixture: for the smoke net the CSV has header p1,p2,p3,p4,p5,p6 and
   exactly 1503 data rows (D-009); the row 7,4,2,5,4,3 (µ0) is present; every
   row is a reachable marking; no row exceeds the per-place maxima
   [10, 8, 16, 29, 8, 10] (D-010).
3. The file is downloadable (server-provided per A-11) and parses as CSV with
   a consistent column count.

Source: task item 5 (export markings CSV); A-11.

### FR-022 — Session history

The application stores session history: ingested nets and their analyses
persist and can be revisited.

Acceptance criteria:

1. Each successfully analyzed net is stored as a session (identifier,
   creation time, net definition, computed results) in the SQLite database at
   `$DB_PATH` (D-016, A-09).
2. The UI lists past sessions; selecting one reopens it — the net
   visualization, the reachability graph, the properties panel, and the
   exports are restored without recomputation from scratch.
3. Sessions persist across container restarts (the database file lives on the
   `petri-data` volume).
4. Deletion: a deleted session disappears from the list endpoint and from subsequent loads; requesting its state returns a typed 404 error; its step history is not recoverable.

Source: task item 6; D-016; A-09.

## 4. Non-functional requirements

### NFR-001 — Performance (smoke net)

Acceptance criteria:

1. For the smoke net (Section 5), full reachability-graph construction (1503
   markings, 4983 edges) completes in under 10 s inside the app container
   (D-009), measured from the start of the analysis run, with the default
   `REACH_MAX_MARKINGS` (50000).
2. The same run's property computation (FR-007…FR-014) completes within the
   same 10 s budget for the smoke net.
3. The measurement is performed in the containerized environment of
   NFR-005 (no host installs involved).

Source: project policy (Phase 2 agent brief); D-009.

### NFR-002 — `REACH_MAX_MARKINGS` safety cap

Acceptance criteria:

1. Reachability construction aborts once the number of discovered markings
   would exceed `REACH_MAX_MARKINGS` (default 50000, D-020, A-15).
2. The abort is reported as a typed API error: structured JSON error body
   with a machine-readable code and HTTP 4xx status — not a crash, timeout,
   or 500.
3. The UI shows a readable (Russian) error and offers switching to
   Karp–Miller (coverability) mode (FR-006 criterion 4).
4. `REACH_MAX_MARKINGS` is configurable via environment variable (NFR-004);
   the smoke net (1503 markings) completes at the default cap.

Source: D-020; A-15; `.env.example`.

### NFR-003 — Structured JSON logging

Acceptance criteria:

1. All application log output is structured JSON (one JSON object per line,
   including at least timestamp, level, and message fields).
2. `LOG_LEVEL` (DEBUG | INFO | WARNING | ERROR, default INFO) selects the
   verbosity and is honored at runtime.
3. Log output contains no user credentials or secrets (the app has no
   secrets; net definitions may appear in logs at DEBUG only).

Source: `README.md` (Configuration); `.env.example`.

### NFR-004 — Configuration via environment variables

Acceptance criteria:

1. All runtime settings are read from environment variables via
   pydantic-settings: `APP_PORT` (default 8080), `LOG_LEVEL` (default INFO),
   `DB_PATH` (default `/data/sessions.db`), `REACH_MAX_MARKINGS` (default
   50000).
2. Every variable has a default; the app starts with no `.env` file at all.
3. `.env.example` documents every variable (name, default, meaning).
4. The container listens on 8000 internally; the host port is `APP_PORT`
   (default 8080) (D-015, A-10).

Source: `README.md`; `.env.example`; D-015; A-10.

### NFR-005 — Containerized development and run

Acceptance criteria:

1. Development, execution, and all quality checks run inside Docker
   containers; nothing is installed on the host except Docker itself (A-14,
   D-017).
2. `sudo docker compose up --build` (run from `petri-net-web/`) serves the
   complete app at `http://localhost:8080` (default `APP_PORT`).
3. Quality gates — pytest, ruff, mypy — are runnable inside the `app`
   container per the README check commands (D-018).
4. No step in the documented workflow requires a package install on the host.

Source: A-14; D-015, D-017, D-018; `README.md` (Checks).

### NFR-006 — Russian UI

Acceptance criteria:

1. All user-facing UI text (labels, buttons, headings, messages, error text)
   is in Russian (A-01, D-001).
2. Technical identifiers (place/transition names such as p1, t1, µ) are
   preserved as entered, untranslated.
3. Project documentation (including this file) remains in English (A-01).

Source: A-01; D-001.

### NFR-007 — Minimal light theme

Acceptance criteria:

1. Styling is minimal; the app uses a light theme.
2. No dark theme is provided or required; absence of one is not a defect
   (task item 8).

Source: task item 8.

### NFR-008 — No CI

Acceptance criteria:

1. The project ships no CI configuration and imposes no CI requirement;
   quality gates are executed manually inside the container (NFR-005).
2. Adding CI later is an out-of-scope change, not a defect of this release.

Source: project policy (Phase 2 agent brief); `README.md` (Checks); D-018.

### NFR-009 — No link sharing

Acceptance criteria:

1. The app provides no share-link / URL feature for sessions or nets (task
   item 7).
2. Sessions are not addressable via public URLs; absence of sharing is not
   a defect.

Source: task item 7.

## 5. Acceptance fixtures

### 5.1 Smoke net — raw text (mandatory parse fixture)

```text
S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3).
```

Semantics: repetition in I/O is arc weight; t is enabled at µ iff
µ(p) ≥ I(t)(p) for all p; firing gives µ' = µ − I(t) + O(t); marking order
follows the declared order of P (T9, A-06).

### 5.2 Smoke net — JSON

```json
{
  "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
  "transitions": ["t1", "t2", "t3", "t4", "t5"],
  "inputs": {
    "t1": {"p1": 2},
    "t2": {"p1": 1, "p6": 1},
    "t3": {"p2": 1},
    "t4": {"p2": 1, "p3": 1, "p4": 2},
    "t5": {"p5": 2}
  },
  "outputs": {
    "t1": {"p2": 1},
    "t2": {"p3": 2},
    "t3": {"p4": 3},
    "t4": {"p5": 1, "p6": 1},
    "t5": {"p1": 1, "p3": 1}
  },
  "initial_marking": {"p1": 7, "p2": 4, "p3": 2, "p4": 5, "p5": 4, "p6": 3}
}
```

### 5.3 Frozen expected results (DECISIONS_LOG.md ground-truth section)

Ground truth was computed in-house on 2026-10-02 by two independent
implementations (BFS with dict-based firing vs DFS with incidence-vector
firing); the reachability sets and edge counts agree exactly (D-003, A-02).
These numbers are the frozen acceptance baseline; any deviation is a defect.

| # | Quantity | Expected value | Decision |
| - | -------- | -------------- | -------- |
| 1 | Reachable markings | 1503 | D-009 |
| 2 | Graph edges | 4983 | D-009 |
| 3 | Per-place maxima p1..p6 | [10, 8, 16, 29, 8, 10] | D-010 |
| 4 | Global bound k | 29 (bounded = true) | D-010 |
| 5 | Safe | false | D-010 |
| 6 | Deadlocks (count) | 23 (list in 5.5; not deadlock-free) | D-011 |
| 7 | Transitions occurring | all five (t1..t5) | D-012 |
| 8 | Transitions at L4 (live) | none (deadlocks break strong liveness) | D-012 |
| 9 | Per-transition levels | all five L3 (each on a reachable cycle; finite graph: L2 <=> L3) | D-012, D-031 |
| 10 | Liveness level (net, min) | L3 | D-012, D-031 |
| 11 | Dead transitions | none | D-012 |
| 12 | Home state / reversibility | false (µ0 not reachable from every marking) | D-013 |
| 13 | Enabled at µ0 | t1, t2, t3, t4, t5 (all) | D-014 |
| 14 | Firing t1 at µ0 | (5, 5, 2, 5, 4, 3) | D-014 |

### 5.4 50-node cyclic net (rendering/performance fixture)

Raw text:

```text
P = {p1..p25}, T = {t1..t25}; for i = 1..25 (cyclic, p26 = p1):
I(t_i) = {p_i}, O(t_i) = {p_{i+1}};
µ0 = (1, 0, ..., 0) (token at p1).
```

JSON equivalent: places p1..p25, transitions t1..t25, inputs {t_i: {p_i: 1}},
outputs {t_i: {p_{i+1}: 1}} (cyclic), initial_marking {p1: 1}.

Frozen expectations (verified against the construction): 25 reachable
markings (the token cycles), 25 edges, per-place maxima all 1 (safe,
1-bounded), no deadlocks, no dead transitions, all 25 transitions live =>
level L4, home state = true.

Source: task item 5 (UI); reviewer fix list.

### 5.5 Smoke net — full deadlock list (23 markings, p1..p6 order)

(1,0,11,18,1,0) (0,0,4,12,0,6) (0,0,12,6,0,2) (0,0,16,3,0,0) (0,0,3,7,1,7)
(0,0,1,5,0,9) (0,0,5,2,0,7) (0,0,5,24,1,3) (0,0,7,4,1,5) (1,0,13,13,0,0)
(0,0,6,14,1,4) (0,0,14,8,1,0) (0,0,10,11,1,2) (0,0,11,1,1,3) (0,0,6,29,0,2)
(0,0,2,17,1,6) (0,0,7,19,0,3) (0,0,10,26,0,0) (0,0,0,0,1,10) (0,0,3,22,0,5)
(0,0,11,16,0,1) (0,0,9,21,1,1) (0,0,8,9,0,4)

### 5.6 Secondary fixture — unbounded net (Karp–Miller validation)

Used to validate FR-006 and the ω-based property reporting (the smoke net is
bounded, so it cannot exercise this path):

- P = {p1}, T = {t1}, I(t1) = {} (empty), O(t1) = {p1: 1}, µ0 = (1).
- Expected: p1 is unbounded (the coverability tree contains ω for p1);
  t1 occurs and is live (enabled at every reachable marking), liveness level
  L4; no deadlocks (deadlock-free = true); not safe, not bounded; home state
  = false (µ0 = (1) is reachable only from itself, while e.g. (2) can only
  grow).

## 6. Traceability matrix

Task items are numbered per the product-owner statement (item 4 sub-letters
4a–4h and item 5 sub-letters 5a–5e are introduced here for granularity;
T9 = the "Semantics" paragraph of the task; the fixture row references the
"Mandatory smoke-test input" paragraph).

| Task item | Requirement(s) |
| --------- | -------------- |
| 1a — intake: raw text notation | FR-001 |
| 1b — intake: JSON per schema | FR-002 |
| 1c — intake: interactive web form | FR-003 |
| 2 — parsing → S = (P, T, I, O, µ) | FR-004 |
| 3 — reachability graph (all markings + transitions) | FR-005 |
| 3 — Karp–Miller coverability tree for unbounded nets (ω) | FR-006 |
| 4a — boundedness (k-bounded per place and global) | FR-007 |
| 4b — safety (safe, k ≤ 1) | FR-008 |
| 4c — liveness (L0–L4) | FR-009 |
| 4d — reachability of specific markings | FR-010 |
| 4e — coverability | FR-011 |
| 4f — deadlocks and dead transitions | FR-012 |
| 4g — reversibility / home state | FR-013 |
| 4h — deadlock-free | FR-014 |
| 5a — net visualization (places, transitions, weighted arcs, tokens) | FR-015 |
| 5b — state-graph visualization, click node → switch marking | FR-016 |
| 5c — step-by-step playback (active transition, step/reset/undo, history) | FR-017 |
| 5d — properties panel | FR-018 |
| 5e — export: graph PNG | FR-019 |
| 5e — export: report JSON | FR-020 |
| 5e — export: markings CSV | FR-021 |
| 6 — session history storage (in-memory or SQLite) | FR-022 (SQLite per D-016) |
| 7 — link sharing NOT needed | NFR-009 |
| 8 — minimal theme, dark not required | NFR-007 |
| T9 — semantics (weights, enablement, firing, marking order) | FR-001, FR-002, FR-004, FR-005 |
| Mandatory smoke-test fixture | Section 5 (criteria in FR-001…FR-022; NFR-001) |
| — performance budget | NFR-001 |
| — REACH_MAX_MARKINGS cap behavior | NFR-002 |
| — structured JSON logging | NFR-003 |
| — config via env (pydantic-settings) | NFR-004 |
| — containerized dev/run, no host installs | NFR-005 |
| — Russian UI | NFR-006 |
| — no CI | NFR-008 |

Coverage: 22 FR + 9 NFR = 31 requirements; every task feature item maps to
at least one requirement with at least one acceptance criterion.

## 7. Out of scope

- Link sharing / public URLs for sessions (task item 7; NFR-009).
- Dark theme or advanced theming (task item 8; NFR-007).
- CI/CD pipelines (NFR-008).
- Multi-user accounts, authorization, and concurrent editing (not in the
  task; single anonymous web session per browser).
- Server-side PNG generation (A-11: PNG export is client-side).
- Nets with infinitely many places/transitions, negative weights, or
  non-integer token counts (invalid per T9/A-08).

## 8. Recorded interpretations (open items for architecture)

These were ambiguous in the task/decisions and are fixed here as the
testable interpretation; the architecture phase may refine wording but must
not change the observable behavior accepted below.

1. **L0–L4 scale (FR-009).** The classical per-transition scale is used
   (Murata; confirmed against Wikipedia "Petri net", Liveness): L0 dead,
   L1 potentially fireable, L2 arbitrarily often, L3 infinitely often in
   some sequence, L4 live (strong, MSU). On a finite reachability graph
   L2 <=> L3 (reachable cycle with a t-edge), so a computed level is never
   exactly L2; the net level is the minimum over transitions. (D-031
   corrected the earlier operational partition.)
2. **Dead transition (FR-012).** Defined as a transition that does not
   occur (never enabled at any reachable marking) — distinct from a
   transition that merely dies later in some run.
3. **Reset semantics (FR-017).** "Reset" returns to µ0 and clears the step
   history; "Undo" keeps the history and pops the last step.
4. **JSON `initial_marking` coverage (FR-002).** Per A-08 the marking must
   cover all places; a missing place is a validation error (not an implicit
   0).
5. **Coverability (FR-011).** Interpreted both as a user query (does a
   reachable marking cover M?) and as ω-based unboundedness detection
   (FR-006/FR-007), matching the two senses in the task and A-03/A-12.
6. **Frozen-number citation.** The agent brief cites "D-008"; in
   `DECISIONS_LOG.md` D-008 is the git-policy decision and the frozen
   ground-truth numbers are D-009…D-014 (the section titled "Ground truth
   for the smoke net"). This document cites the numbers by their actual IDs.
 7. **Session storage medium (FR-022).** The task allows in-memory or SQLite;
  D-016 fixed SQLite — used here as the acceptance requirement.
 8. **FR-002 deferral.** Absent `inputs`/`outputs` keys in JSON input resolve
  to empty maps (weight-0 arcs); the behavior must be consistent between JSON
  and form intake and covered by tests (final wording in the architecture).

## Appendix A — Product-owner task statement (verbatim)

Web application for working with Petri nets:
1. Intake of the net description in three formats:
   a) "raw" text in mathematical notation (example below),
   b) JSON per the schema (to be designed in the architecture phase),
   c) interactive web form (places, transitions, weighted arcs, initial marking).
2. Parsing -> internal representation S = (P, T, I, O, µ).
3. Reachability graph construction: all markings reachable from µ0 + transitions between them. For unbounded nets — Karp–Miller coverability tree (with ω).
4. Property analysis of the graph:
   - boundedness (k-bounded) per place and global;
   - safety (safe, k <= 1);
   - liveness (L0–L4);
   - reachability of specific markings;
   - coverability;
   - deadlocks and dead transitions;
   - reversibility / home state;
   - deadlock-free.
5. UI:
   - visualization of the net (places, transitions, weighted arcs, tokens);
   - visualization of the state graph with click on a node -> switch to that marking;
   - step-by-step "playback": pick an active transition -> new marking, step / reset / undo buttons, step history;
   - properties panel;
   - exports: graph PNG, report JSON, markings CSV.
6. Session history storage allowed (in-memory or SQLite).
7. Link sharing — NOT needed.
8. Theme/styling — minimal, dark theme not required.

Mandatory smoke-test input:

S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3).

Semantics:
- Repetition in I/O = arc weight (I(t1) = {p1, p1} means arc p1->t1 of weight 2).
- t is enabled at µ iff µ(p) >= I(t)(p) for all p. Firing: µ' = µ − I(t) + O(t).
- Marking order follows the declared order of P.

Example JSON schema (to be refined in architecture):

{
  "places": ["p1","p2",...],
  "transitions": ["t1","t2",...],
  "inputs":  { "t1": {"p1": 2}, ... },
  "outputs": { "t1": {"p2": 1}, ... },
  "initial_marking": {"p1": 7, "p2": 4, ... }
}


