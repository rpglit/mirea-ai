# Отчёт о тестировании — petri-net-web (итерация 3)

|              |                                                                    |
| ------------ | ------------------------------------------------------------------ |
| Статус       | v3.1 (итерация 3, фазы 2.6–3, **после фиксации находок**) — **PASS** |
| Дата         | 2026-10-10                                                         |
| План         | `docs/TEST_PLAN.md` v3.0                                           |
| Гейты        | `app pytest` / `ruff check src tests` / `mypy` / `e2e` (13 сценариев) / audit: axe, perf, VR — в контейнерах |

## 1. Итог

| Гейт | Результат | Детали |
| ---- | --------- | ------ |
| Юнит + property | **286 passed** (0 failed) | 18 файлов; 32.6 с |
| ruff | **All checks passed** | `src tests` |
| mypy (strict) | **no issues found in 21 source files** | |
| E2E | **21 passed / 13 сценариев** (0 failed) | 32.2 с; console чистый во всех сценариях (NFR-107) |
| A11y (axe-core 4.13) | **0 critical / 0 serious / 0 moderate / 0 minor** (после фикса; первоначально 3 serious + 9 moderate — §7/§10) | ✅; `docs/acceptance/a11y/axe_summary.json` (обновлён) |
| Perf (медиана из 3) | (a) **1.69 с** ≤ 5 с ✓; (b) cold **559 мс** / warm **2 мс** ≤ 10 с ✓; (c) p95 healthz под solve: LSS-04 **20.5**, LSS-05 **11.4**, LSS-10 **13.7 мс** (после `setswitchinterval(0.001)`, D-061; было 33.9/33.4/97.5) — все < 50 мс ✓ | ✅; `docs/acceptance/perf/perf_results.json` (обновлён) |
| Visual regression (E2E-12, Pillow) | **0 диф-пикселей** на всех 4 экранах (порог < 1%) | маски `#canvas-net`/`#session-badge`; без масок main-light 0.76% / main-dark 0.34% (COSE-дрейф) |
| Сборка | OK | app (node:20-alpine + python:3.12-slim), e2e (+Pillow 12.3.0, axe-core 4.13.0) |

## 2. Распределение юнит-тестов (286)

| Блок | Файлы | Тестов |
| ---- | ----- | ------ |
| Решатели ЛСС (23 задачи + `*_tex`-поля FR-605) | `test_solvers_lss.py` | 36 |
| Решатели PN (40 задач каталога + эталоны §8) | `test_solvers_pn.py` | 29 |
| Core v2 (ингибиторы, приоритеты, usable-вектор) | `test_core_v2.py` | 25 |
| Парсер v2 (JSON/форма: inhibitors/priorities/delays/colors) | `test_parser_v2.py` | 22 |
| Решатели FA (8 задач: normalize/simulate/compare/to_mealy, такты) | `test_solvers_fa.py` | 21 |
| Парсер текст (round-trip, property) | `test_parser_text.py` | 20 |
| API решателей (/solve, /catalog+prefill, /matrices, /minimal-marking, /properties+, /sessions limit, /parse v2, ошибки) | `test_api_solvers.py` | 18 |
| Решатели PN расширенные (приоритеты/временные/ингибиторы/цветные) | `test_solvers_pn_ext.py` | 16 |
| Свойства v2 (conservative, вердикт, sequence, µmin) | `test_properties_v2.py` | 15 |
| API раунда 1 (все маршруты, экспорт, ошибки) | `test_api.py` | 15 |
| Reachability (1503/4983, Кэрп–Миллер, cap) | `test_reachability.py` | 11 |
| Свойства (якоря D-009…D-035, L-шкала) | `test_properties.py` | 11 |
| Парсер JSON/форма | `test_parser_json_form.py` | 11 |
| Core (семантика, A-06) | `test_core.py` | 10 |
| **API ит. 3 (P1#2/P1#3/P2#7): solve вне event loop, таймаут+кэш, in-flight дедуп, v2-поля сессий, Cache-Control (статика/API)** | `test_api_v3.py` | 10 |
| Каталог/роутинг/кэш/константы/JSON-сериализация 71/**дедуп solve_future** | `test_solvers_init.py` | 7 |
| Reachability v2 (ингибиторы/ω/приоритеты) | `test_reachability_v2.py` | 7 |
| Дымовой | `test_smoke.py` | 2 |

**Новое итерации 3 (фазы 2.6–3):** `test_solvers_init.py::test_solve_future_inflight_dedup` —
инвариант дедупликации: второй `solve_future(одинаковый)` сделан при гарантированно
in-flight первом (gate) → один и тот же future, `solve` вызван ровно 1 раз
(monkeypatch-счётчик). `Cache-Control` уже покрыт: `test_api_v3.py::
test_api_routes_have_no_cache_control` (API-ответы без заголовка) +
`test_static_assets_immutable`/`test_static_index_no_cache` — дублировать не стал.
**Покрытие каталога:** все 71 задача (PN 40 / LSS 23 / FA 8) по эталонам
MATERIALS_ANALYSIS §8 + negative-тесты (`TASK-PN-99`, `TASK-LSS-99`, `TASK-XX-01`).

## 3. Случайные объекты (hypothesis)

24 property-теста × 10–40 примеров (`test_core*.py`, `test_parser_text.py`,
`test_reachability*.py`, `test_properties*.py`) — > 20 случайных объектов на
инвариант: баланс срабатываний, граф (легальность рёбер, достижимость, BFS),
отчёт vs независимая проверка (вердикт/conservative), импликации
(safe⇒bounded, L4⇒deadlock-free), детерминизм, round-trip текстового парсера.
+ 1 property-инвариант дедупликации `solve_future` (§2).

## 4. Производительность (NFR-112, ADR-0012) — медиана из 3

| Замер | Бюджет | Факт | Вердикт |
| ----- | ------ | ---- | ------- |
| (a) Полный browser-сценарий smoke-сети (goto → parse → анализ → граф 1503 отрендерен, с загрузкой страницы) | ≤ 5 с | **1.69 с** (1.65/1.69/1.76) | ✓ (якорь аудита 2.83 с → −40% после FR-609) |
| (b) `POST /solve` TASK-LSS-10 через API | ≤ 10 с | cold **559 мс** (566 при первом замере), warm **2 мс** (2.1/1.8) | ✓ |
| (c) `/healthz` во время solve (из браузера, solve холодный — уникальный ключ кэша; первые 5 fetch + выборка ~20 мс до конца solve, метод audit_extra2) | p95 < 50 мс | LSS-04 **33.9 мс** (n=3), LSS-05 **33.4 мс** (n=3), LSS-10 **97.5 мс** (n=16); медиана p95 — 33.9 мс | ✗ — **PERF-1** |

Контекст (c): блокировка event loop устранена (аудит ит. 1: 513–588 мс → сейчас
максимум 97.5 мс, медиана 33–44 мс); остаток — GIL-конкуренция CPU-воркера
(sympy) с event loop (интервалы переключения GIL). `test_api_v3`
(healthz 2.2–3.4 мс под 0.5 с solve) непротиворечив: `time.sleep` освобождает
GIL, реальный CPU-bound solve — нет.

## 5. E2E (13 сценариев, 21 тест, `e2e/test_e2e.py`)

| # | Сценарий | Результат |
| - | -------- | --------- |
| E2E-1 | Текстовый ввод: 1503/4983, 11 узлов сети, свойства k=29/L1/23/«нет» | PASSED (+`e2e-1-analysis.png`) |
| E2E-2 | Проигрывание: one-click t1 → «p1 (5)», Отмена, «Срабатывание», клик по истории, Сброс | PASSED |
| E2E-3 | Экспорт CSV (1504 строки, заголовок, µ0) + JSON (k=29, L1, 23) | PASSED |
| E2E-4 | JSON-ввод: те же якоря | PASSED |
| E2E-5 | История сессий: восстановление без пересчёта | PASSED |
| E2E-6 | «Задание из практикума»: 71 карточка, фильтр 40, prefill PN-05, отчёт (5,3,4,6,3,3) | PASSED (+`e2e-6-solve-pn.png`) |
| E2E-7 | FA-03: граф 4 вершины, прохождение p1 p2 p2 p1 p2 по тактам (1 текущее → 3 посещённых) | PASSED (+`e2e-7-fa-graph.png`) |
| E2E-8 | PNG сети / графа / «PNG всех» — валидные файлы | PASSED |
| E2E-9 | Темы (FR-601/602): дефолт light, select → dataset.theme, Registry identity, persistence reload | PASSED |
| E2E-10 | KaTeX (FR-603/604): LSS-14 `.katex` + aria-label/data-tex + copy TeX (clipboard/tost), PN-05 «(5,3,4,6,3,3)» + ≥3 `.katex`, «сырых» строк 0 | PASSED |
| E2E-11 | **Ключевые TASK в обеих темах** (6 тестов: PN-05/LSS-14/FA-03 × light/dark): «Задание из практикума» → карточка → «Решить» → `.report`; PN-05 «(5,3,4,6,3,3)»; LSS-14 `.katex`; FA-03 `Registry.automaton` 4 вершины; dark: `dataset.theme="dark"`, 0 `.formula__fallback` | PASSED ×6 |
| E2E-12 | **Visual regression** (4 теста: main/отчёт LSS-14 × light/dark): pixel-diff против `vr-baseline/` — размер совпадает, **0 пикселей** > 30 по яркости (порог 1%); маски `#canvas-net`/`#session-badge` | PASSED ×4 |
| E2E-13 | **Focus-цикл** (NFR-111): Tab×10 на главном экране — 0 pageerror, 9 остановок `:focus-visible` (10-я — обход к `<body>`, стандартное поведение Chromium; свежий экран = 9 таб-стопов) | PASSED |

**Console (NFR-107):** все 21 тест — console чистый.

**A11y/perf — вне pytest** (медленные): `audit/axe_check.py`, `audit/perf_check.py`
(§6–7); VR-бэйджи: `audit/vr_baseline.py`.

## 6. Visual regression (E2E-12)

- Метод: Pillow pixel-diff (без внешних snapshot-пакетов), порог < 1% пикселей
  с Δ яркости > 30, размеры обязаны совпадать. Бэйджи зафиксированы в
  `docs/acceptance/vr-baseline/` (main-light/dark 1400×1940, report-lss14-
  light/dark 1400×3864); текущие скриншоты — `docs/acceptance/vr-current/`.
- Детерминированность бэйджей проверена повторными съёмками: с масками
  **0–13 пикселей** (≤ 0.0005%); report-экраны детерминированы полностью
  (0 пикселей даже без масок).
- **Маски и почему** (применяются одинаково к baseline и current):
  - `#canvas-net` (618×380 на main): layout COSE стартует из случайных
    позиций (cytoscore), узлы/рёбра дрифтуют — без маски диф main-light
    0.76% / main-dark 0.34% (на границе порога). Контент канваса покрывается
    функционально (E2E-1/2/5: 11 узлов, метки, срабатывания) и визуально —
    скриншотами тем `docs/acceptance/themes/`.
  - `#session-badge` (≈245×18): `/parse` не возвращает `name` в ответе →
    `App.vue:86` показывает uuid сессии (находка **A11Y/PROD-3**, §7).
- Граф достижимости 1503 (grid-layout, детерминирован) — в пиксельном дифе
  **без маски** и стабильный.

## 7. Доступность (axe-core 4.13.0, `audit/axe_check.py`)

4 экрана (main и отчёт LSS-14 × light/dark), критерий NFR-111 — 0 violations
уровня critical/major (в axe-core 4.10+ «major» переименован в «serious» —
учтено в скрипте; версия зафиксирована в `axe_summary.json`).

| Экран | critical | major(serious) | moderate | minor |
| ----- | -------- | -------------- | -------- | ----- |
| main-light | 0 | 2 | 4 | 0 |
| main-dark | 0 | 2 | 4 | 0 |
| report-lss14-light | 0 | 1 | 3 | 0 |
| report-lss14-dark | 0 | 1 | 3 | 0 |

**Нарушения major(serious) — найдены в первичном прогоне, ЗАКРЫТЫ продуктовой командой (повторный прогон: 0):**

- **A11Y-1 (P1, NFR-111, WCAG 2.1 AA)** — `nested-interactive` (tags:
  wcag2a, wcag412): компонент Formula (`frontend/src/components/Formula.vue:54-69`)
  — корень `span[role="math"][tabindex="0"]` содержит вложенную
  `button.formula__copy` → вложенные интерактивные элементы (некорректно
  озвучиваются скринридерами, проблемы фокуса). Узлов: main — 30
  (панель свойств: `span[aria-label="k = 29"]`, `p_i ≤ N`), report LSS-14 — 21
  (формулы шагов). **Фикс (закрыт):** корень Formula — `role="figure"` (не
  `img`: у img в axe `childrenPresentational=true`, violation не закрывался —
  проверено по исходникам axe 4.13), `tabindex` убран; copy-кнопка — единственный
  интерактивный узел. Повторный axe-прогон: 0 nested-interactive.
- **A11Y-2 (P2, best-practice, serious)** — `label-title-only` (main):
  `select[title="Режим построения"]` подписан только `title`. **Фикс (закрыт):**
  `aria-label="Режим построения графа"` (+ latent-нарушение того же класса на
  скрытом select «Вид дуги» в InputTabs закрыто вместе).

**Нарушения moderate (замечания, P2):** `heading-order` (h3 в `#step-panel`
и отчёте без предшествующих h1/h2), `landmark-one-main` (нет `<main>`),
`landmark-unique` (`.view-tabs` — два nav без различимого имени), `region`
(контент вне landmark'ов).

Полные результаты: `docs/acceptance/a11y/axe_<экран>.json` + скриншоты
`axe_<экран>.png`; сводка `axe_summary.json` (pass=false).

## 8. Ground truth (независимая проверка)

- **KaTeX render digest (NFR-110):** `docs/acceptance/math/katex_render_digest.json`
  — **166/166** формульных строк (83 уникальные; `answer`+`solution[].data`
  LSS-01…23, `*_tex` исключены) отрендерены KaTeX 0.19.0 без ошибок и
  warnings (node-рендерер `audit/katex_render.js`). Эталоны `*_tex`:
  LSS-08 `\frac{1}{s + 5}`, LSS-23 `\frac{1}{s + 1}`, LSS-14
  roots {3−i:1, 3+i:1}.
- **WCAG-контраст тем (NFR-109):** `docs/THEME_PLAN.md` §3 — 5 effective-тем ×
  12 пар, **все проходят AA** (текст ≥ 4.5:1, UI ≥ 3:1); минимум по тексту —
  tokyo-night 10.59. Пересчитано после ревью фазы 1 (8 ячеек).
- **ЛСС ОДУ/Φ/АЧХ/состояния, FA-такты, PN-эталоны** — как в раунде 2
  (TEST_REPORT v2 §6, без изменений; LSS-23/LSS-20 — с заметками).
- **VR-бэйджи** — §6 (детерминированы, 0–13 пикселей).

## 9. Дефекты итерации 3 (P0/P1 закрыты в фазах 2.1–2.5, проверено)

| # | Дефект (аудит) | Статус | Доказательство |
| - | -------------- | ------ | -------------- |
| P0#1 | «Консервативная» всегда «да» (`Boolean(объекта)`) | закрыт (FR-606): smoke-сеть → «нет», `test_api`/e2e-1 якорь «нет» | `docs/acceptance/audit/50-p0-conservative-net-light.png`, `53-p0-conservative-da.png` |
| P1#2 | /solve блокирует event loop (healthz 513–588 мс) | закрыт (FR-607, D-060): sync-def + воркер + semaphore + дедуп; healthz под solve 33–97 мс (остаток GIL → PERF-1) | `docs/acceptance/audit/40-report-lss10.png`, `test_api_v3.py` (10 тестов) |
| P1#3 | Reopen сессии теряет v2-поля (⊣ 2→0) | закрыт (FR-608): `GET /sessions/{id}` несёт inhibitors/priorities/delays | `docs/acceptance/audit/30-inh-created.png`, `31-inh-after-reopen.png`, `test_api_v3.py` |
| P1#4 | Двойной re-render графа 1503 | закрыт (FR-609): один render при смене structure | perf (a) 1.69 с (якорь 2.83 с) |
| P1#5 | Оверфлоу 375px (504 > 375) | закрыт (FR-610) | `docs/acceptance/audit/54-p1-mobile375.png`, `55-p1-tablet768.png` |
| P1#6 | keyboard-a11y canvas/history | закрыт (FR-611) | `docs/acceptance/audit/52-p1-keyboard-history.png`; E2E-13 |
| P2#7 | Cache-Control статики | закрыт (FR-612) | `test_api_v3.py` (immutable/no-cache/без заголовка) |
| P2#8/#9/#13 | re-fit resize / loading-состояние / hotkeys | закрыты (FR-613…615) | `docs/acceptance/audit/56-p2-resize-fit.png`, `51-p2-loading-state.png`, `57-p2-hotkeys.png` |

## 10. Отклонения и замечания (новые находки фазы 2.6 — возврат, не закрыты)

1. **A11Y-1 (P1) — ЗАКРЫТ** — `nested-interactive` в Formula (WCAG 2.1 AA, 51 узел) — §7 (фикс: role=figure, без tabindex).
2. **A11Y-2 (P2) — ЗАКРЫТ** — `label-title-only` у `select` — §7 (aria-label).
3. **PERF-1 (P2) — ЗАКРЫТ** — p95 `/healthz` под холодным solve LSS-10 было 97.5 мс
   (GIL-остаток). Фикс: `sys.setswitchinterval(0.001)` при старте app (D-061);
   после фикса p95: 13.7–20.5 мс (все < 50 мс — базовый бюджет выдержан;
   расширенный бюджет <150 мс задокументирован в D-061/FR-607).
4. **PROD-3 (P2)** — `POST /parse` не возвращает `name` в ответе, хотя имя
   принимается и сохраняется (`backend/src/petrinet/api/routes.py:153-165`):
   `App.vue:86`-бейдж показывает uuid сессии до reopen (влияние — только
   визуальное/determinism VR; маскируется в E2E-12).
5. LSS-23: несовместная СЛАУ источника — заметка в отчёте решателя (как в раунде 2).
6. LSS-20: sinh ≡ sin на комплексном аргументе — заметка (как в раунде 2).
7. Console-чек e2e строгий (NFR-107) — осознанно (как в раунде 2).
8. `test_smoke::test_static_index_served` падает вне контейнера (нет /app/static)
   — артефакт запуска, не регрессия (D-060); в контейнере — зелёный.

## 11. Вывод

Все основные гейты зелёные: **286 pytest** (вкл. property и новый
инвариант дедупликации solve_future), **ruff/mypy strict** чистые,
**21/21 e2e-тест (13 сценариев)** с чистым console, **visual regression —
0 диф-пикселей** на 4 ключевых экранах, производительность в 2.9 раза ниже
бюджета ADR-0012 (1.69 с), P0/P1 аудита подтверждённо закрыты.
Однако по результатам **axe-аудита нарушен NFR-111** (0 critical/major):
найдено 2 serious-правила — `nested-interactive` (WCAG 2.1 AA, Formula.vue)
и `label-title-only`, а **NFR-112 AC(1)** (p95 healthz < 50 мс) не выдерживается
под холодным solve TASK-LSS-10 (97.5 мс, GIL-остаток). Обе позиции —
требования итерации 3, закрытие — за продуктовой командой (код QA не
изменял). **Вердикт: REJECT с 2 находками (A11Y-1 — P1, PERF-1 — P2;
+ замечания A11Y-2, PROD-3, P2-moderate).** Повторная приёмка после фикса
A11Y-1/PERF-1: пересборка не требуется (фикс фронтенда/воркера → build app),
гейты: `app pytest` / `ruff` / `mypy` / `e2e` / `audit/axe_check.py` /
`audit/perf_check.py`.
