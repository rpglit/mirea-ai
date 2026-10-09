# Аудит petri-net-web — итерация 3 (Фаза 1.1)

- **Дата:** 2026-10-09
- **Роль:** audit-agent (только отчёт, без правки продуктового кода)
- **Контракт:** `.opencode/agents/audit-agent.md`
- **Объект:** `http://localhost:8080` (host) / `http://app:8000` (в e2e-контейнере). App healthy.
- **Стек:** Vue 3 (Composition API) + Vite + Cytoscape (npm) — `frontend/src/`; FastAPI — `backend/src/petrinet/`.
- **Методы:** чтение кода, standalone Playwright-скрипты (`e2e/audit/`, НЕ pytest), замеры
  `performance.now()` / Resource-Timing в браузере, API-замеры через `urllib`,
  `npm audit` (node:20-alpine, сборочный этап), `pip-audit` (в контейнере app),
  HTTP-заголовки статики.
- **Артефакты:** скрипты `e2e/audit/audit_{ui,api,extra,extra2,inhibitor,terms}.py`;
  скриншоты и JSON-дайджесты — `docs/acceptance/audit/`.

Запуск скриптов (только контейнеры, без установок на хост):

```
sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_ui.py"
sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_api.py"
sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_extra.py"
sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_extra2.py"
sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_inhibitor.py"
sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_terms.py"
```

---

## Сводная таблица проблем (16)

| # | Проблема | Слой | Приоритет | Шаги воспроизведения | Предлагаемое решение | Оценка |
|---|----------|------|-----------|----------------------|----------------------|--------|
| 1 | «Консервативная» **всегда** «да»: `yesNo(Boolean(r.conservative))`, но `r.conservative` — объект, не bool | код (UI) | **P0** | Текст-интейк → «Проанализировать» (smoke-сеть) → строка «Консервативная» в таблице свойств | Читать внутренний флаг: `Boolean(r.conservative?.conservative)` (API отдаёт `{per_transition,constant_sum,conservative}`) | S |
| 2 | `POST /solve` блокирует event-loop: `async def` + синхронный CPU-`solvers.solve()` → `/healthz` и весь API «зависают» на время solve (до 30 с = cap) | API/производительность | **P1** | Открыть задачу LSS-10 → «Решить»; параллельно мерить `/healthz` | Перевести solve в threadpool (`run_in_threadpool`) либо sync `def`; таймаут — не SIGALRM (он только на main-поток), а лимит итераций/`concurrent.futures` | M |
| 3 | При повторном открытии сессии (`GET /sessions/{id}`) **теряются** `inhibitors`/`delays`/`priorities`/`colors` → перерисованная сеть неверна (⊣-дуги 2→0) | код (API) | **P1** | Ввод формы с ингибиторами → анализ → «История сессий» → открыть ту же сессию | Добавить в ответ `get_session` поля `inhibitors/delays/priorities/colors` (они уже в `model_json`) и маппить в `store.model` | M |
| 4 | Лишние полные ре-рендеры графа достижимости: и `watch(structure)`, и `watch(deadlocks)` вызывают `render()` (destroy+recreate+layout) → граф на 1503 узлах лейаутится **дважды** за один анализ | код (UI/производительность) | **P1** | «Проанализировать» (smoke) → в `window.__audit.sets` две записи `graph=cy` | Разделить: `deadlocks`/`current` — лёгкое обновление классов без пересоздания; полный `render` только при смене `structure` | S |
| 5 | Горизонтальный оверфлоу на 375px: таблица свойств тянет `scrollWidth` страницы до 504px (> 375) → горизонтальный скролл на мобильном | UI/адаптивность | **P1** | Viewport 375×667 → анализ → появляется горизонтальный скроллбар | `table-layout:fixed`/`max-width:100%` + `overflow-wrap` для столбцов, либо `overflow-x:auto` у контейнера таблицы; media-query на стекинг | S |
| 6 | Клавиатурная доступность: канвасы Cytoscape и строки истории **не таbable** (нет `tabindex`/`role`); goto по графу и восстановление шага истории — только мышью | доступность | **P1** | Tab-цикл: фокус идёт select → кнопки → … но никогда не падает на `.history-line` и на канвас | Дать `.history-line` `role="button"`+`tabindex`+Enter/Space; канвас — `tabindex`+обработка стрелок/Enter (или отдельный focusable-список узлов) | M |
| 7 | Статика без `Cache-Control`: JS-бандл Vite 563KB и CSS отдают только `ETag`/`Last-Modified` → нет агрессивного кеша неизменяемых ассетов | производительность | P2 | `curl -sI /assets/index-*.js` → нет заголовка `Cache-Control` | Для `*/assets/*` — `Cache-Control: public, max-age=31536000, immutable`; для `index.html` — `no-cache` | S |
| 8 | Граф не пере-фитится при ресайзе окна: при сужении контейнера `extent` сжимается и часть графа уходит за край (нет re-fit) | UI | P2 | Анализ → сузить окно до ~700px → граф частично обрезан | Слушатель `resize` (ResizeObserver) → `cy.fit()` / `cy.resize()` по канвасу | S |
| 9 | Мгновенно после анализа шаг-панель врёт «нет разрешённых переходов» и гасит «Срабатывание» до ответа `/state` (нет loading-состояния) | UX | P2 | «Проанализировать» → в момент появления «узлов: 1503» active ещё `[]` | Вести флаг `stateLoading`; до ответа `/state` показывать «…», а не пустое состояние | S |
| 10 | Неполное e2e-покрытие «Задания из практикума»: нет сценария LSS-группы, «Сохранить в сессию», редактирования JSON-данных, «Закрыть» | код (тесты) | P2 | `e2e/test_e2e.py` — E2E-6/7/8 покрывают только PN и FA | Добавить e2e: solve LSS + проверка формул; save-to-session; solve с изменёнными данными; close | M |
| 11 | Дублирование кода: загрузка PNG (`ExportMenu.downloadBlob`/`pngOf` и `ReportPanel.exportAutomatonPng`); `compactTuple`/`tupleEquals` (store.js) дублируют `compactMarking`/`sameMarking` (ReachabilityCanvas) | код | P2 | Сравнить `ExportMenu.vue:9-27` с `ReportPanel.vue:141-160`; `store.js:55-64` с `ReachabilityCanvas.vue:17-24` | Вынести общий `downloadBlob`/`cyToPng` и переиспользовать `compactTuple`/`tupleEquals` из store | S |
| 12 | `pip 25.0.1` (build-инструмент) — 12 уязвимостей (PYSEC-2026-*); frontend npm: **0** уязвимостей (vue/cytoscape/vite чистые) | безопасность/производительность | P2 | `pip-audit` в контейнере app | Обновить базовый образ / `pip install -U pip` (низкий риск: pip только в сборке) | S |
| 13 | Нет hotkeys (никаких клавиатурных сокращений для «Проанализировать»/«Срабатывание»/«Отмена») | UX | P2 | Пробел/Enter/Ctrl+Enter ничего не делают | Минимальный набор: Ctrl/⌘+Enter — анализ, F5-подобные для step/undo/reset | S |
| 14 | В отчёте «Задания из практикума» **нет** пояснений терминов (в отличие от таблицы свойств, где есть колонка «Пояснение») | UX/терминология | P2 | Открыть TASK-LSS-10 → разделы Дано/Найти/Решение/Ответ без пояснений | Добавить tooltip/подсказку или колонку-справку по терминам глоссария §5 | M |
| 15 | Терминология: в целом **совпадает** с глоссарием §5; единичные пограничные: «Тупики» (список маркировок) vs «тупиковая сеть» (свойство); «Мёртвые переходы» — отрицание «Достигаемого перехода» | терминология | P2 | Строки «Тупики»/«Мёртвые переходы» в таблице свойств vs `MATERIALS_ANALYSIS.md` §5.1 | Связать/уточнить формулировки со ссылкой на определения глоссария | S |
| 16 | На 375px канвас сети ~166px шириной: сеть из 64+ узлов неразборчива без зума | UI/адаптивность | P2 | Viewport 375 → анализ big-сети (32 позиции) | Media-query: стекинг канвасов, управляемый зум/«подогнать», или горизонтальный скролл канваса | S |

Итого: **P0 — 1, P1 — 5, P2 — 10** (16 проблем).

---

## Детализация P0 / P1 (с acceptance criteria)

### #1 (P0) — «Консервативная» всегда «да»
- **Факт:** API отдаёт `conservative` как объект `{per_transition:{...}, constant_sum:bool, conservative:bool}`
  (`backend/src/petrinet/api/routes.py:267`, `backend/src/petrinet/properties.py:47,399`).
  UI делает `yesNo(Boolean(r.conservative))` — `Boolean(объект)` всегда `true`.
- **Доказательство:** для smoke-сети `POST /properties` → `conservative.conservative = false`
  (t1: in 2 / out 1), но в UI строка «Консервативная» = «да»
  (скриншоты `docs/acceptance/audit/02-analysis-1503.png`, `07-keyboard-focus.png`).
- **Файл:** `frontend/src/components/PropertiesPanel.vue:68`.
- **Решение:** `value: yesNo(Boolean(r.conservative && r.conservative.conservative))`.
- **Acceptance criteria (измеримые, e2e-проверяемые):**
  1. Для smoke-сети текст строки «Консервативная» в `#props` === «нет» (сейчас «да»).
  2. Для консервативной сети (например, цикл p1→t1→p2→t2→p1, µ=(1,0)) — «да».
  3. Юнит/e2e: `props_text(page)` содержит «Консервативная» + «нет» для smoke.

### #2 (P1) — `/solve` блокирует event-loop
- **Факт:** `solve_task` объявлен `async def` и синхронно вызывает CPU-тяжёлый `solvers.solve()`
  (`backend/src/petrinet/api/routes.py:408-431`). Уvicorn выполняет `async def` на event-loop →
  цикл блокируется на время solve. Таймаут через `SIGALRM` работает только на main-потоке,
  поэтому простой перевод в sync `def` сломает лимит — нужен иной механизм.
- **Доказательство (`audit_extra2.py` → `event_loop_block_sampled`):** baseline `/healthz` ≈ 0.7–1.1 ms;
  во время solve `TASK-LSS-10` (542.8 ms) сэмпл `/healthz` = **513.4 ms**; `TASK-LSS-20` (148.7 ms) → 119.3 ms;
  `TASK-PN-08` (164.4 ms) → 135.1 ms. В худшем случае (cap 30 с) healthcheck (`timeout: 3s`, `retries: 5`)
  упадёт → контейнер unhealthy.
- **Решение:** `await run_in_threadpool(solvers.solve, ...)` (или sync `def`-эндпоинт) + таймаут без SIGALRM
  (лимит итераций/`future.result(timeout=…)` в worker-потоке).
- **Acceptance criteria:**
  1. Во время solve `TASK-LSS-10` p95 задержки `/healthz` < 50 ms (сейчас ~513 ms).
  2. Параллельный `POST /parse` отвечает за < 200 ms, пока идёт solve.
  3. При solve > 30 с возвращается 500 `solver_failed`, а event-loop жив (healthz отвечает).

### #3 (P1) — повторное открытие сессии теряет v2-поля
- **Факт:** `get_session` (`backend/src/petrinet/api/routes.py:786-822`) возвращает только
  `places/transitions/inputs/outputs/current_marking/...` и **не возвращает** `inhibitors/delays/priorities/colors`,
  хотя они хранятся в `model_json`. Frontend `loadSession` кладёт этот summary в `store.model`
  (`frontend/src/components/NetView.vue:238-274`), и сеть перерисовывается без ⊣-дуг.
- **Доказательство (`audit_inhibitor.py`):** до reopen `inhibitor: 2` + подпись «(⊣ — ингибиторная дуга)»;
  `get_session_has_inhibitors: false`; после reopen `inhibitor: 0`, подпись исчезла
  (скриншоты `30-inh-created.png` / `31-inh-after-reopen.png`). Аналогично пропадают `delays/priorities/colors`.
- **Решение:** добавить в ответ `get_session` поля из `model_json` (`inhibitors/delays/priorities/colors`),
  маппить в `store.model`; не менять `model_to_json`.
- **Acceptance criteria:**
  1. `GET /sessions/{id}` для сети с ⊣ содержит `inhibitors` (ключ присутствует, значения = исходные).
  2. После reopen из «Истории сессий» `window.Registry.net.edges('[direction="inhibitor"]').length` == до reopen (2 в тесте).
  3. Скриншот после reopen содержит подпись «(⊣ — ингибиторная дуга)».

### #4 (P1) — двойной полный re-render графа достижимости
- **Факт:** `ReachabilityCanvas` имеет `watch(() => props.structure, render)` **и**
  `watch(() => props.deadlocks, render)` (`frontend/src/components/ReachabilityCanvas.vue:187-189`),
  где `render()` = destroy + recreate + layout. `deadlocks` = `store.report?.deadlocks`
  (`NetView.vue:31-34`), меняется после `/properties` → второй полный layout того же графа.
- **Доказательство (`audit_ui.py` → `perf_full_1503.registry_sets`):** две записи
  `{key:"graph", created:true}` (t≈829 и t≈2080) за один анализ — граф на 1503 узлах лейаутится дважды.
  Client total ≈ 2829 ms при том, что сам API-график лёгкий (см. бюджет ниже).
- **Решение:** `deadlocks`/`current` обновлять через `toggleClass`/`data` без `render()`; полный
  `render` — только при смене `structure` (или при явном «Построить граф»).
- **Acceptance criteria:**
  1. За полный анализ `window.__audit.sets` содержит ровно **одну** `graph=created` (не две).
  2. Время client full-analysis smoke (1503) снижается минимум на стоимость одного layout (замер до/после в `audit_ui.py`).
  3. e2e E2E-1..E2E-8 остаются зелёными, console чистый (NFR-107).

### #5 (P1) — горизонтальный оверфлоу на 375px
- **Факт:** на мобильной ширине таблица свойств не сжимается: `document.documentElement.scrollWidth` = **504** при
  `clientWidth` = **375** → горизонтальный скроллбар. Широчайший элемент — `#props.props-table` (488px)
  (`audit_extra2.py` → `mobile375_cause.wide`).
- **Доказательство:** скриншот `docs/acceptance/audit/20-mobile375-analysis.png` (виден горизонтальный скролл).
- **Решение:** `table-layout:fixed; width:100%` + `overflow-wrap:anywhere` на ячейках (особенно «Значение»/«Пояснение»),
  либо `overflow-x:auto` у `#props-panel`; media-query для стекинга канвасов.
- **Acceptance criteria:**
  1. При viewport 375×667 после анализа `scrollWidth <= clientWidth` (нет горизонтального скролла).
  2. Все 3 колонки таблицы свойств читаемы без зума (скриншот-регрессия).

### #6 (P1) — клавиатурная доступность (canvas + история)
- **Факт:** строки истории — `<div class="history-line" @click>` без `tabindex`/`role`
  (`frontend/src/components/StepPanel.vue:64-74`); канвасы Cytoscape — обычные `<div>`, goto по узлу графа
  — только `tap` (`ReachabilityCanvas.vue:158-166`). Клавиатурный пользователь не может восстановить шаг
  истории и не может перейти к маркировке по графу.
- **Доказательство (`audit_extra.py` → `keyboard_tab_order`):** `reached_canvas: false`,
  `reached_history_line: false`. При этом сам «Срабатывание» с клавиатуры работает
  (`keyboard_fire_enter.history_lines: 1` — Enter по фокусированной `.btn-transition` сработал).
- **Решение:** `.history-line` → `role="button"`, `tabindex="0"`, обработчик Enter/Space; канвас графа →
  `tabindex` + навигация стрелками по узлам + Enter = goto (или доступный список узлов-кнопок).
- **Acceptance criteria:**
  1. Tab-цикл доходит до `.history-line` (`reached_history_line: true` в `audit_extra.py`).
  2. Enter на сфокусированной `.history-line` восстанавливает шаг (изменяется `current_marking`).
  3. Есть клавиатурный способ goto (фокус на графе/списке + Enter) — `current` узел меняется.

---

## Терминология (UI и отчёты vs глоссарий `MATERIALS_ANALYSIS.md` §5)

Сравнены все видимые строки (таблица свойств, отчёт «Дано/Найти/Решение/Ответ», вкладки, подписи) с §5.1–5.3.

**Вывод: терминология в целом консистентна.** Совпадают ключевые термины:
- PN: «Живая сеть/тупиковая/частичнотупиковая» (§5.1), «k-ограниченная», «Безопасная», «Консервативная»,
  «Разрешённый переход», «Срабатывание», «Маркировка µ», «Дуга/кратность», «Граф достижимости».
- LSS: «A(ω) — амплитудно-частотная характеристика» (АЧХ), «φ(ω) — фазо-частотная характеристика» (ФЧХ),
  «Φ(s) — передаточная функция», «P(λ) — характеристический многочлен», «y_о/y_ч», «весовая функция g(t,τ)».
- FA: «Перечисление (φ, ψ)», «Таблица переходов», «Граф автомата», «Эквивалентный автомат Мили», «Автоматный такт».

**Пограничные/единичные расхождения (→ пункт #15, P2):**
- «Тупики» (в UI — список конкретных маркировок-мёртвых состояний) vs глоссарий «Тупиковая сеть»
  (свойство сети). Концепции разные; подпись в UI допустима, но стоит пометить связь с определением.
- «Мёртвые переходы» — отрицание термина глоссария «Достигаемый переход»; в §5.1 «мёртвый переход»
  прямо не определён (определён через «L0 — мёртвая» в пояснении уровня живости).
- «Обратимость (home state)» — термин home state из ADR-0004, в глоссарии §5.1 не вынесен отдельной строкой.
- «Дискретная (ω) приближённая оценка» (плашка `#props-caveat`) — формулировка не дословно из глоссария.

**Нет** грубых подмен/непереводов; англо-русских «островков» в пользовательских строках не обнаружено.

---

## Производительность — фактические замеры (якоря)

| Метрика | Значение | Источник |
|---------|----------|----------|
| Full-analysis smoke (1503 узлов) **client** | **≈ 2830 ms** (клик → граф+свойства готовы) | `audit_ui.py perf_full_1503` |
| — из них API `/graph` (1503) server | 46.9 ms | `audit_api.py smoke_pipeline_ms` |
| — `/properties` server (smoke) | 18.6 ms | `audit_api.py` |
| — `/parse` + `/state` server | 6.1 + 1.2 ms | `audit_api.py` |
| Итого smoke-пайплайн **server** | **72.8 ms** | `audit_api.py` |
| Якорь in-process build (см. ТЗ) | ~0.04 s | `/graph` server 46.9 ms — того же порядка |
| Якорь «e2e-сценарий ~3 с» (см. ТЗ) | client 2830 ms | совпадает (~3 с) |
| **Бутылочное горло** | двойной client-layout графа 1503 (пункт #4) + `cose`/`breadthfirst` | `registry_sets` |
| Big-сеть 32 позиции (64 узла канваса, 32 узла графа) | `/graph` 158 ms, `/properties` 38 ms, канвас 64/32 узла | `audit_ui.py perf_big32` |
| `POST /solve` — все 71 задачи каталога | **0 падений**; суммарно 3406 ms | `audit_api.py solve_all` |
| — самая тяжёлая | `TASK-LSS-20` 934.5 ms; `TASK-LSS-10` 825.8 ms; `TASK-PN-08` 158 ms | `audit_api.py solve_all.top10_heaviest` |
| Healthz baseline | 0.7–1.1 ms | `audit_extra2.py` |
| Healthz **во время solve** | до **513 ms** (LSS-10) | `audit_extra2.py` (пункт #2) |
| Статика: JS бандл | 563 267 байт, **без** `Cache-Control` (только ETag/Last-Modified) | `audit_api.py static_cache` (пункт #7) |
| `GET /sessions?limit=50` | 43.6 ms (50 строк) | `audit_api.py sessions_list` |

**Вывод по бюджету:** server-часть в пределах якорей (smoke ~0.07 s in-process, solve < 1 с).
Превышение «~3 с» на клиенте объясняется не API, а **двойным лейаутом** графа 1503 (#4) и
отсутствием агрессивного кеша статики (#7). Закрытие #4+#7 должно уложить повторные загрузки заметно ниже 3 с.

---

## Positive findings (что проверено и в норме)
- **Console чистый (NFR-107):** 0 ошибок/0 warning на всех сценариях, включая переключения
  «Сеть Петри» ⇄ «Задание из практикума», решение задач, возврат (`audit_ui.py view_switch_console: 0`,
  `console: []`).
- **npm audit: 0 уязвимостей** (vue 3.5.43, cytoscape 3.34.3, vite 6.4.4).
- **e2e-селекторы-контракт** (`window.Registry.{net,graph,automaton}`, `#input-text`, `#btn-run-text`,
  `#tab-json`, `#input-json`, `#btn-run-json`, `#btn-step`, `#btn-undo`, `#btn-reset`,
  `#active-list .btn-transition`, `#history-list .history-line`, `#btn-export-*`, `#btn-sessions`,
  `#sessions-list .session-item`, `#graph-stats`, `#props`) — все присутствуют и работают.
- **Тупиковое состояние** отображается корректно: 23 deadlock-узла, «нет разрешённых переходов»,
  «Срабатывание» гаснет (`audit_extra2.py deadlock_state`).
- **Cap/coverability** работает: неограниченная сеть → `/graph` auto = 413 `cap_exceeded`
  (suggestion `coverability`), `coverability` = 1 ω-узел; `delays` → 422 `unsupported_model`
  с понятным RU-сообщением (`audit_api.py cap_and_coverability`, `delays_graph`).
- **Big-сеть (32 позиции)** собирается и анализируется без ошибок (64/32 узла).
- **Экспорты** PNG/JSON/CSV и сессии работают (e2e E2E-3/5/8 зелёные).

---

## Открытые вопросы для оркестратора
1. **#2 (event-loop /solve):** согласовать механизм таймаута без `SIGALRM` (он привязан к main-потоку,
   а исправление требует threadpool). Варианты: `future.result(timeout)` в воркере / лимит итераций / процесс.
   Нужна ли гарантия «не убивать» solve раньше 30 с?
2. **#3 (v2-поля при reopen):** достаточно ли добавить поля в `GET /sessions/{id}`, или фронтенд должен
   ходить в `GET /sessions/{id}/graph` + отдельный endpoint модели? (Минимально — дополнить summary.)
3. **#4 (двойной re-render):** можно ли менять `deadlocks`/`current` на лёгкое обновление, не трогая
   замороженный e2e-контракт `window.Registry.graph` (инстанс остаётся тем же — контракт не ломается).
4. Приоритет P2: какие 3–5 из P2 брать в итерацию вместе с P0/P1 (кеш статики #7 и hotkeys #13 — дешёвые).
5. Нужно ли зафиксировать `package-lock.json` (сейчас версии vue/cytoscape/vite плавают по `^`)?
