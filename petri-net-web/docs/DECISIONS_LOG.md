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
- **D-012** Transitions: all five occur (enabled somewhere). Classical
  L0–L4 scale (D-031): all five are **L1** (occurs, but NO reachable cycle
  contains any t-edge — see D-035), none is L4 (the 23 reachable deadlocks
  break strong liveness). Net liveness level (min over transitions): **L1**.
- **D-013** Home state / reversibility: **False** — µ0 is not reachable from every
  reachable marking.
- **D-014** At µ0 all transitions t1..t5 are enabled; firing t1 at µ0 gives
  (5,5,2,5,4,3). (Anchors used by core/api tests.)

Deadlock list (p1..p6 order, lexicographic tuple-sorted — canonical report
order per D-022; the set is unchanged):
(0,0,0,0,1,10) (0,0,1,5,0,9) (0,0,2,17,1,6) (0,0,3,7,1,7) (0,0,3,22,0,5)
(0,0,4,12,0,6) (0,0,5,2,0,7) (0,0,5,24,1,3) (0,0,6,14,1,4) (0,0,6,29,0,2)
(0,0,7,4,1,5) (0,0,7,19,0,3) (0,0,8,9,0,4) (0,0,9,21,1,1) (0,0,10,11,1,2)
(0,0,10,26,0,0) (0,0,11,1,1,3) (0,0,11,16,0,1) (0,0,12,6,0,2) (0,0,14,8,1,0)
(0,0,16,3,0,0) (1,0,11,18,1,0) (1,0,13,13,0,0)

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

## Phase 3 (architecture, 2026-10-02)

- **D-022** Canonical ordering of `deadlocks` in reports: lexicographic
  (tuple-sorted). The D-011 list was re-emitted in this order (same 23
  markings; the original order was an arbitrary iteration order of the
  ground-truth script). The reviewer caught the contradiction with the
  "discovery order" claim in ARCHITECTURE.md.
- **D-023** `POST /graph` returns the full deterministic structure
  (`structure.nodes = [[id, marking]...]`, `structure.edges =
  [[src_id, transition, dst_id]...]`, ADR-0002 ids) — the UI renders from the
  response and the structure is stored on the session (ADR-0005) and reused by
  `/properties`, `/goto`, CSV export.
- **D-024** Report contract gains `bounded: bool` (all places bounded; true
  for the smoke net) — required by FR-007 c2 / FR-018 c1 / FR-020 c1.
- **D-025** DESIGN_BRIEF fixes (brief was an orchestrator input, ADR/
  ARCHITECTURE is authoritative): Cytoscape net-canvas edge data =
  `{weight, source, target}`; `POST /goto` added to the brief's route table.
  Also: `inputs`/`outputs` are NOT required in the JSON schema (absent = empty
  maps, ADR-0003 / REQUIREMENTS §8.8) — the brief's "required" list was wrong.
- **D-026** Process deviation: in this session large sub-agent dispatches fail
  silently (empty result, no artifacts) while small per-file dispatches work.
  Workaround: `docs/DESIGN_BRIEF.md` (orchestrator-pinned decisions) + one
  deliverable per dispatch. The orchestrator applied the Phase-3 review fixes
  (6 mandatory) directly instead of re-dispatching; ADR-0002 pseudocode walk
  simplified; throwaway `0000-healthcheck.md` ADR removed.
- **D-027** `jsonschema>=4.21` added to backend dev extras (image rebuilt);
  the schema file validates against both fixtures (schema-valid: ok;
  smoke-fixture: ok).

## Phase 4 (implementation, 2026-10-02)

- **D-028** Runtime JSON schema lives in the package:
  `backend/src/petrinet/schema.json` (package data, loaded by parser.py);
  `docs/schemas/petri-net.schema.json` is the documented mirror (byte-equal,
  checked in the Phase-4.1 review).
- **D-029** Form intake payload shape pinned (parse_form docstring):
  `{places, transitions, arcs: [{source, target, weight, direction:
  "input"|"output"}], initial_marking}`; "input" = place->transition arc,
  "output" = transition->place; duplicate (direction, source, target) is a
  validation error.
- **D-030** `build(net, mode="auto", cap=50000)` — the contract gained an
  optional `cap` keyword (default 50000); the API layer passes the configured
  `REACH_MAX_MARKINGS`. Justified contract extension: the core module is
  framework-free and must not read settings.
- **D-031** **LIVENESS CORRECTION.** The classical per-transition L0–L4 scale
  (Murata; confirmed via Wikipedia "Petri net" Liveness section) replaces the
  earlier A-05 operational partition: L0 dead / L1 occurs / L2 arbitrarily
  often / L3 infinitely often in some sequence / L4 live (strong, MSU). On a
  finite reachability graph L2 <=> L3 (reachable cycle with a t-edge), so a
  computed level is never exactly L2; net level = min over transitions.
  Corrected ground truth: see D-035 (the first correction attempt claimed
  "all L3" from a buggy script — superseded). Updated: A-05, ADR-0004
  (rewritten), REQUIREMENTS FR-009 + §5.3 + §8.1 + glossary, ARCHITECTURE
  (Report contract + sample report), D-012.
- **D-032** Process deviation (recurring): in this session sub-agent
  dispatches for complex single files (parser.py x3, reachability KM part,
  full-module multi-file tasks) fail silently (empty result, no artifacts)
  while small per-file dispatches succeed. Fallback: the orchestrator writes
  the file from the pinned spec; quality gates (pytest/ruff/mypy) and the
  reviewer-agent still run unchanged. Affected so far: `parser.py`.
- **D-033** Node ids serialized as strings `"n<index>"` in the API
  (contract shape); the earlier integer example in the /graph response was
  corrected before implementation.
- **D-034** The Karp–Miller builder honors the same cap as the graph builder
  (safety device). Measured 2026-10-02: the coverability tree of the bounded
  smoke net grows to 1.9M+ nodes in 20 s (path-local subsumption duplicates
  labels across branches — exponential blow-up, a known KM pathology); for
  unbounded nets the tree is small because ω compresses it (counter: 1 node).
  Cap hit in coverability mode -> typed 413 `cap_exceeded`. Updated:
  ADR-0002, ARCHITECTURE reachability contract, FR-006 criterion 5.
- **D-035** **GROUND-TRUTH CORRECTION #2 (liveness direction bug).** The
  first L3 verification script checked `m ->* m2` (trivially true for the
  edge itself) instead of the correct `m2 ->* m`, and reported "all L3".
  Corrected computation (forward reachability per edge, plus the container's
  Tarjan SCC on the built graph — all 1503 nodes singleton): **no reachable
  cycle contains any transition**. Independent proof: the weighted potential
  W = 3·p1 + 4·p2 + p3 + p4 + 3·p5 + 2·p6 strictly decreases under every
  transition (t1: -2, t2: -3, t3: -1, t4: -2, t5: -2) — the reachability
  graph is a DAG; every firing sequence is finite and ends in one of the 23
  deadlocks. True levels: all five transitions **L1**, net level **L1**;
  home state stays false (only µ0 reaches µ0: 1/1503). Updated: D-012,
  FR-009 c4, §5.3 rows 8-10, FR-018 c2, ADR-0004 example 1, ARCHITECTURE
  sample report + properties bullets, agent files (L3 -> L1). The
  properties module code needed no change (its SCC/closure logic was
  correct — it simply found no cycles).

## Phases 5-6 (QA + acceptance, 2026-10-02)

- **D-036** Cytoscape is vendored: `frontend/vendor/cytoscape.umd.js`
  (3.30.2), served by the app at `/vendor/cytoscape.umd.js`. The runtime CDN
  dependency (unpkg) hung page loads in the offline e2e container; vendoring
  removes the external dependency entirely.
- **D-037** e2e container base: `ubuntu:24.04` + python3 venv +
  `playwright==1.49.1` + `playwright install --with-deps chromium`. The
  `mcr.microsoft.com/playwright/python:v1.49.1-jammy` image no longer ships
  the python playwright package; `python:3.12-slim` (Debian) fails
  `--with-deps` on Ubuntu-only font package names.
- **D-038** API extension for session restore: `/parse` and
  `GET /sessions/{id}` responses now carry `inputs`/`outputs` arc maps (the
  net canvas needs them); `GET /sessions/{id}/graph` returns the stored
  structure (no recomputation). +1 test.
- **D-039** Phase 5 results: 80 unit/property tests green, ruff rc=0, mypy
  strict clean (12 files), e2e 5/5 green (~9 s). Defects found+fixed during
  Phase 5 are listed in docs/TEST_REPORT.md section 4.
- **D-040** Phase 6 acceptance: the full web path (Playwright -> UI -> API ->
  storage -> exports) produced `docs/acceptance/` artifacts; the 1503-marking
  CSV set-equals the independent stdlib ground truth (no duplicates); the
  report matches D-009..D-014/D-035. Verdict: ACCEPT (TEST_REPORT.md).

## Раунд 2 (2026-10-08): прицел на задания методички

- **D-041** Запуск второго раунда. Новая цель: приложение УВЕРЕННО РЕШАЕТ ВСЕ задания из архива методички (формат и терминология методички) и ЛЮБЫЕ аналогичные задания. Ответы Фазы 0: архив «Практические занятия-20261008.zip» (20 PDF) распакован в `/home/ipetrichenko/mirea-ai/materials/`; язык UI и документации — русский; отчёты — формулировки методички + пояснение своими словами; backend FastAPI остаётся; API прежнего раунда ломать можно (main один); лимит эскалации — 3 итерации сабагента.
- **D-042** Стек фронтенда (ответ на Q5 «посовременнее и покрасивее, но не сильно сложнее»): **Vue 3 (script setup) + Vite** (сборка — отдельный node-этап в Dockerfile app) + **Cytoscape.js** для графиков (проверен в проекте; портировать логику net/reachability-графов дешевле, чем переписывать на D3). Итоговый выбор и ADR — Фаза 3 (architect-agent).
- **D-043** Материалы вне git: `/home/ipetrichenko/mirea-ai/materials/` и исходный zip — локальные файлы корня (политика корня: только ноутбуки/датасеты/исходное задание). Артефакты анализа — внутри `petri-net-web/docs/` (коммитятся).
- **D-044** Покрытие курса — ТРИ предметные области (выявлено анализом архива): **PN** — сети Петри (семинары 1–8), **LSS** — линейные непрерывные системы: ОДУ/весовая функция/передаточная функция/АЧХ-ФЧХ/пространство состояний (семинары 9–12), **FA** — дискретно-детерминированные модели (F-схемы): конечные автоматы (семинары 13–15). Каталог: **71 задача** (PN 40, LSS 23, FA 8) — `docs/MATERIALS_ANALYSIS.md`. Открытый вопрос: сужать ли фокус до PN (зафиксировано в ASSUMPTIONS A-17).
- **D-045** Результаты Фазы 1. 4 materials-agent (партии A–D) — полное извлечение 20 PDF (207 стр.) → `docs/materials/raw/batch-A..D.md`. Сведение в `MATERIALS_ANALYSIS.md` выполнено ОРКЕСТРАТОРОМ напрямую: 3 попытки сабагентов-интеграторов вернули пустой результат (нестабильность на больших задачах — паттерн раунда 1). reviewer-agent: найден и исправлен 2 неверных эталона «проверено, не из источника» (TASK-PN-05: итог (5,3,4,6,3,3); TASK-PN-17: итог (0,0,1)), неточное «Дано» TASK-FA-07, сбивчивая формулировка TASK-PN-18 и 6 мелочей. Вердикт после исправлений — PASS.
- **D-046** Дедупликация редакций (установлено batch-агентами текстовым сравнением): актуальные = 2025/2025(new); `11-12.pdf` (без года) — дубликат 11-2025 (сходство 98%); `13-2025.pdf` (21 стр.) = сшитый «13-2025(new) ∪ 14-2025(new)»; `11-2024.pdf` — 2024-редакция темы F-схем (математически идентична 13/14/15-2025); `13-2024.pdf` («Классификация сетей Петри») и `13-14.pdf` (без года, непрерывные системы) — ДРУГИЕ темы под номерами 2025-плана; их задачи вкатаны в каталог как «старые редакции» областей PN и LSS.
- **D-047** Результаты Фазы 2 (GAP-анализ, compatibility-agent ×2 + reviewer). PN: 21/40 решается, 14/40 частично, 5/40 не решается (проверено живым прогоном на работающем приложении: PN-05 целиком, PN-17/18/35 по срабатываниям, PN-04/09 по свойствам — все совпали с эталонами MATERIALS_ANALYSIS §8). LSS/FA: 0/31 — модулей нет. UI: 10 багов (1 critical — PNG-экспорт: `cy.png()` в Cytoscape 3.30.2 без `output` возвращает строку; 3 major — подписи весов дуг (невалидный селектор), подсветка текущего узла, терминология панели свойств; 6 minor). Терминология: главное расхождение — шкала живости L0–L4 vs классификация методички живая/тупиковая/частичнотупиковая + отсутствие «консервативная». Артефакты: `docs/GAP_ANALYSIS.md` (сводный), `docs/GAP_BACKEND.md`, `docs/GAP_UI.md`, `e2e/debug_gap.py`, скриншоты `docs/acceptance/gap/`. Приоритеты Фазы 4: properties-дополнения (консервативность/µmin/W±/вердикты) → расширенные модели (ингибиторы/Pr/τ/CPN/параллелизм) → solvers (LSS sympy, FA, отчёты PN) → api → UI на Vue 3.
- **D-048** Результаты Фазы 3. REQUIREMENTS.md переписан на русском (158 строк): 39 FR + 8 NFR, трекируемость 71/71 TASK-XX (каждый ID ровно один FR-решатель); FR-3xx — решатели по областям (PN: классификация/моделирование/матрицы/Минский/расширенные; LSS: ОДУ/весовая/передаточная/АЧХ-ФЧХ/пространство состояний; FA: автоматы/моделирование/эквивалентность); форматы отчётов {task_id, given, find, solution, answer, notes}. ARCHITECTURE.md переписан (481 стр., русский): core v2 (ингибиторы ⊣, Pr, τ, цвета, fire_set), properties+ (conservative/verdict/µmin/W±), solvers пакет (pn/lss-sympy/fa) с Report, api (POST /solve, GET /catalog, POST /matrices, POST /minimal-marking, русские ошибки, имена сессий, limit 50), фронтенд Vue 3 + Vite + Cytoscape (дерево компонентов, PNG `output:'blob-promise'`), ADR 0007–0010. Ключевые решения: τ-симуляция по тактам в solvers (core без времени); цветовые/временные сети — только симуляция (графы → 422); PN-02 «достроить сеть» = кандидат-сеть, которую пользователь принимает в сессию. Requirements-агент: первая попытка — пустой результат, вторая — успех (итерация 2/3). reviewer: PASS с 2 правками (пайп в таблице ARCH:220, FR-022→FR-406) — внесены.
- **D-049** Шаг 4.2 (core v2) закрыт: PetriNet v2 (+inhibitors/priorities/delays/colors с дефолтами None — порядок полей: initial_marking перед опциональными, т.к. dataclass-правило; сниппет ARCH §2.1 поправлен), enabled(usable=), fire_set (ConflictError, русские сообщения), active (макс Pr в конфликтной группе), incidence (W−,W+,W), minimal_marking (parallel=True — сумма требований всех переходов, worst case; уточнение внесено в ARCH). 25 новых тестов (19 юнит + 6 hypothesis, эталоны PN-05/07/09/35), всего 105/105, ruff/mypy strict чисто. reviewer: PASS с замечаниями (все устранены). Legacy `__str__` ошибок переводится на русский на шаге 4.6 (api).
- **D-050** Шаг 4.1 (parser v2) закрыт: schema.json v2 (+inhibitors/priorities/delays/colors, опциональные, additionalProperties:false) + зеркало docs/schemas/ (байт-в-байт); pass-2: ключи ∈ T, позиции ∈ P, пары delays — только ВЫХОДНЫЕ дуги, τ≥1, colors keys ∈ T/P; parse_form: direction:"inhibitor" (вес принудительно 1), priorities, delays; parse_text без изменений (классическая грамматика методички). 22 новых теста (в т.ч. delay на входную дугу — добавлен по ревью), всего 127/127, ruff/mypy чисто. Отклонения: inhibitor без веса = 1; priorities без перехода = 0.
- **D-051** Шаг 4.3 (reachability v2) закрыт (оркестратором напрямую — сабагент вернул пустой результат без артефактов): `UnsupportedModelError` (delays/colors → 422 в любом режиме, до построения); BFS наследует ингибиторы через core.enabled (приоритеты множества достижимых не меняют — расширение идёт по enabled, не active); Кэрп–Миллер: ω (или натуральное >0) в позиции-ингибиторе блокирует переход навсегда (проверка при расширении узла); сохранено поведение round 1 «метка узла в момент извлечения» (pop-time label) — это классическая запись KM, обеспечивающая полноту покрытия (свежая метка после промоушена внутри расширения дала бы неполное дерево — проверено на сети с разовым t3). Якоря 1503/4983 и одно-ω узел — зелёные. 8 новых тестов (включая hypothesis: рёбра BFS = enabled/fire core; unbounded-случай → CapExceeded как валидный исход), всего 134/134, ruff/mypy чисто.
- **D-052** Шаг 4.4 (properties v2) закрыт: conservative (оба определения методички: Σвх(t)=Σвых(t) на каждом t + постоянная сумма по узлам структуры; ω → false), sequence_report (шаги core.fire, v(σ), µ′=µ+W·v(σ) через core.incidence, executable/failed_at), verdict — ТРИ класса методички «по продолжительности работы»: «живая» ⇔ L4; «тупиковая» ⇔ граф — DAG (все цепочки конечны); «частичнотупиковая» ⇔ есть циклы, но не все переходы живые; coverability → None. Старые критерии ARCH («deadlocks≠∅») заменены: контрпример — 2-компонентная сеть (живой самозамыкающий компонент + компонент с тупиком): тупиковых маркировок нет, но часть переходов работает бесконечно, а часть — нет → по методичке «частичнотупиковая», по старым критериям вышло бы «неживая» (класса, которого в методичке нет). Report + conservative (всегда) + verdict + mu_min (по запросу, core.minimal_marking). 15 новых тестов (эталоны PN-05/07/09/17/35, Пример 8, 2-компонентная, coverability), всего 149/149, ruff/mypy чисто, якоря раунда 1 (L1/k=29/23/home=false) зелёные; устаревший docstring-якорь «L3» в properties.py поправлен на «L1» (находка GAP-ревью).
