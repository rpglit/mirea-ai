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

## Раунд 2 (материалы методички, 2026-10-08)

- **A-17** Объём курса: архив охватывает 3 области (PN/LSS/FA). Цель 2 раунда — «решать ВСЕ задания из архива» → каталог и решатели покрывают все 3 области; если пользователь сузит фокус до PN — приоритеты Фазы 4 перераспределяются (зафиксировать в D-xxx), каталог остаётся полным.
- **A-18** «F-схемы» в материалах не расшифрованы; по содержанию = конечные автоматы (Мура/Мили) — используется это прочтение.
- **A-19** ЛНДС = «линейные непрерывно-детерминированные системы» (расшифровка есть в тексте семинара 9, стр. 1).
- **A-20** «Минимальная маркировка для срабатывания всех переходов» (TASK-PN-07/09/19): в материалах только постановки; формализация — покомпонентный максимум требований I(tj) по всем переходам (для параллельного срабатывания — сумма требований конфликтующих переходов).
- **A-21** Цветные сети (TASK-PN-36/37) и временные сети (TASK-PN-32): в материалах — примеры без числовых эталонов; формализация решателя — стандартные определения (гварды — булевы выражения над значениями меток; задержки на дугах от переходов, по умолчанию 1).
- **A-22** TASK-FA-07: каноническое чтение таблицы задания — состояния z0,z1,z2; выходы ψ(z0)=y2, ψ(z1)=ψ(z2)=y1 (повтор «y1» в шапке легитимен); переходы — по клеткам таблицы (x1: z0→z1, z1→z0, z2→z1; x2: z0→z2, z1→z2, z2→z2). Альтернативное чтение «состояния — y» отвергнуто (клетки не лежат в этом множестве).
- **A-23** TASK-FA-08: y-метки дуг в графе задания не согласованы с правилом Мура однозначно; принятое чтение: φ — по дугам, ψ — по меткам вершин (ψ(Z0)=y1, ψ(Z1)=y2, ψ(Z2)=y1).
- **A-24** Язык документации нового раунда — русский (ответ Фазы 0). Существующие английские доки раунда 1 (REQUIREMENTS, ARCHITECTURE, ADR, TEST_PLAN/REPORT) переписываются/дополняются на русском в Фазе 3.
- **A-25** Факты, помеченные в MATERIALS_ANALYSIS.md как «проверен, не из источника», до использования в приёмке пересчитываются независимо (Фаза 5); в раунде 2 reviewer уже верифицировал PN-03/04/05/06/07/09/17/18/21, LSS-06/07.
