# План тестирования — petri-net-web (итерация 3)

|            |                                                                                          |
| ---------- | ---------------------------------------------------------------------------------------- |
| Статус     | v3.0 (итерация 3, фазы 2.6–3)                                                            |
| Дата       | 2026-10-10                                                                               |
| Источники  | `docs/REQUIREMENTS.md` (раунд 2: FR-1xx…FR-5xx, NFR-1xx; итерация 3: §7 FR-601…615, §8 NFR-109…112), `docs/ARCHITECTURE.md` (ADR-0001…0012), `docs/THEME_PLAN.md` (токены, WCAG-таблица), `docs/MATH_RENDER_PLAN.md` (KaTeX), `docs/AUDIT_REPORT.md` (16 проблем), `docs/DECISIONS_LOG.md` (D-041…D-060), `docs/MATERIALS_ANALYSIS.md` (§3 каталог, §8 эталоны) |

План пишется до прогона; результаты — в `docs/TEST_REPORT.md`. Якорные значения
заморожены в REQUIREMENTS/MATERIALS_ANALYSIS/DECISIONS_LOG/ADR — любое
расхождение — дефект, а не «несоответствие плану».

## 1. Цели и область

### В области (итерация 3 поверх раундов 1–2)

- **Темы оформления (FR-601/602, NFR-109)**: 6 тем (light/dark/system/
  tokyo-night/catppuccin-mocha/synthwave84), переключатель в шапке,
  persistence `localStorage["pn-theme"]` без FOUC (анти-FOUC inline-скрипт в
  `<head>`), 45 токенов `--pn-*`, JS-палитры Cytoscape (canvas не читает
  CSS-переменные), рестил `cy.style()` на живом инстансе без destroy/re-layout
  (`window.Registry.*` сохраняются), WCAG 2.1 AA во всех effective-темах.
- **Рендеринг формул (FR-603…605, NFR-110)**: KaTeX 0.19.0 локально (npm, без
  CDN), компонент Formula (`role="math"`, `aria-label`/`title`/`data-tex` = TeX,
  copy TeX: clipboard → execCommand-fallback → тост; fallback `.formula__fallback`
  при битом TeX без console-ошибок), 14 точек Formula, аддитивные `*_tex`-поля
  бэкенда (sp.latex, детерминизм), клиентский tex.js (PN/FA).
- **Фиксы аудита (FR-606…611)**: «Консервативная» из объекта отчёта (P0#1),
  `/solve` вне event loop: sync-def + daemon-воркер + `BoundedSemaphore(4)` +
  in-flight дедупликация + таймаут `future.result(30 с)` (P1#2), v2-поля
  `GET /sessions/{id}` (P1#3), единый render графа 1503 (P1#4), без
  горизонтального оверфлоу 375px (P1#5), клавиатурная доступность истории/
  графа (P1#6).
- **P2-фиксы (FR-612…615)**: `Cache-Control` статики (middleware), re-fit при
  resize, loading-состояние шаг-панели, hotkeys.
- **Наследие раундов 1–2 (без изменений, регрессия)**: семантика сети + v2-поля
  (ингибиторы/приоритеты/задержки/цвета), 3 канала ввода, граф достижимости +
  Кэрп–Миллер, свойства (boundedness/safety/k, liveness L0–L4, тупики, home,
  conservative, вердикт, µmin), решатели 71 задачи (PN 40 / LSS 23 / FA 8),
  API (все маршруты + `/solve`, `/catalog`, `/matrices`, `/minimal-marking`,
  `/properties+`, `/sessions?limit`, `/parse` v2), UI Vue 3 + Vite + Cytoscape
  (оба экрана), экспорт PNG/JSON/CSV, сессии (SQLite).

### Вне области

- CI-пайплайны (гейты запускаются вручную в контейнерах).
- Нагрузочное тестирование (NFR-101 — бюджет одиночного запуска; perf-аудит —
  точечные замеры, не нагрузка).
- Безопасность (аутентификации нет, секретов нет).
- Юнит-тестирование JavaScript (vitest не вводится): KaTeX-хелперы и tex.js
  покрываются e2e (E2E-10/11), digest-скриптом и axe/perf-аудитами.
- Хост-окружение: всё в Docker (NFR-106).

## 2. Окружение

Всё в Docker-контейнерах; команды — из `/home/ipetrichenko/mirea-ai/petri-net-web`.

| Сервис | Образ | Примечания |
| ------ | ----- | ---------- |
| `app`  | `backend/Dockerfile`: node:20-alpine (сборка Vite) + python:3.12-slim | порт 8080→8000, healthcheck `/healthz`, SQLite на томе `petri-data`; исходники — в образе (COPY), после изменения `backend/` — `docker compose build app && docker compose up -d app` |
| `e2e`  | `e2e/Dockerfile` (ubuntu:24.04 + Playwright Python 1.49.1 + headless Chromium + **Pillow 12.3.0** + **axe-core 4.13.0** (`/opt/axe`, npm)) | `BASE_URL=http://app:8000`; `./docs/acceptance` → `/e2e/screenshots`; `./e2e` → `/e2e` |

Канонические команды:

| Гейт | Команда |
| ---- | ------- |
| Сборка | `sudo docker compose build` |
| Запуск app | `sudo docker compose up -d app` |
| Юнит + property | `sudo docker compose run --rm app pytest` |
| Lint | `sudo docker compose run --rm app ruff check src tests` |
| Типы (strict) | `sudo docker compose run --rm app mypy` |
| E2E (13 сценариев) | `sudo docker compose run --rm e2e` (app — healthy) |
| A11y-аудит (axe-core, медленный) | `sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/axe_check.py"` |
| Perf-аудит | `sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/perf_check.py"` |
| VR-бэйджи (пересоздание) | `sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/vr_baseline.py"` |

## 3. Матрица тестов

| Слой | Техника | Где | Что покрывает |
| ---- | ------- | --- | ------------- |
| unit | Детерминированные + замороженные фикстуры | `test_core*.py`, `test_parser*.py`, `test_reachability*.py`, `test_properties*.py` | Семантика (вкл. ингибиторы/приоритеты), 3 канала ввода + v2, граф 1503/4983, Кэрп–Миллер ω, свойства (якоря D-009…D-035, conservative, вердикт, µmin, sequence_report) |
| property | Гипотезы (hypothesis) | те же файлы (`@given`), 24 теста × 10–40 примеров | 20+ случайных объектов на инвариант: баланс срабатываний, согласованность отчёта с независимым пересчётом, легальность рёбер графа, детерминизм, safe⇒bounded, L4⇒deadlock-free, round-trip текстового парсера |
| property | Инвариант дедупликации | `test_solvers_init.py` (`test_solve_future_inflight_dedup`) | Два параллельных `solve_future(одинаковый)` — ровно один запуск `solve` (monkeypatch-счётчик + gate, второй вызов — при гарантированно in-flight первом; один и тот же future) |
| unit | Решатели | `test_solvers_lss.py` (36, вкл. `*_tex`-поля FR-605), `test_solvers_pn.py` (29), `test_solvers_pn_ext.py` (16), `test_solvers_fa.py` (21), `test_solvers_init.py` (7: каталог/роутинг/кэш/JSON-сериализация 71/дедуп) | Все 71 задача каталога по эталонам MATERIALS_ANALYSIS §8; отчётная форма Дано/Найти/Решение/Ответ; custom-группы; ошибки (UnknownTask/Validation/Cap); кэш; константы лимитов |
| unit | API | `test_api.py` (15), `test_api_solvers.py` (18), `test_api_v3.py` (10) | Все маршруты + итерация 3: `/solve` вне event loop (healthz <50 мс под 0.5 с solve, таймаут→500+кэш, in-flight дедуп через HTTP), `GET /sessions/{id}` v2-поля (inhibitors/priorities/delays, классическая сеть — ключи отсутствуют), `Cache-Control` (`/assets/*` immutable, index `no-cache`, API-ответы — без заголовка) |
| e2e | Браузер (Playwright) | `e2e/test_e2e.py` — **13 сценариев, 21 тест** | E2E-1…E2E-13 (§5) + console-чек NFR-107 во всех сценариях |
| a11y | axe-core 4.13 (audit-скрипт, не в pytest) | `e2e/audit/axe_check.py` → `docs/acceptance/a11y/` | 4 ключевых экрана (main/отчёт LSS-14 × light/dark): критерий NFR-111 — 0 violations уровня critical/major (в axe-core 4.10+ «major» = «serious»); moderate/minor — замечания |
| perf | Точечные замеры (audit-скрипт, не в pytest) | `e2e/audit/perf_check.py` → `docs/acceptance/perf/` | Медиана из 3: (a) полный browser-сценарий smoke-сети ≤ 5 с (ADR-0012/NFR-112); (b) `POST /solve` LSS-10 ≤ 10 с (NFR-101); (c) `/healthz` p95 < 50 мс во время холодного solve (из браузера, метод audit_extra2 + первые 5 fetch) |
| visual regression | Pillow pixel-diff (E2E-12) | `e2e/vr.py`, `e2e/audit/vr_baseline.py` → `docs/acceptance/vr-baseline/` | 4 экрана (main/отчёт LSS-14 × light/dark): размер страницы совпадает, < 1% пикселей отличается > 30 по яркости; маски — `#canvas-net` (COSE стартует из случайных позиций — дрейф ~0.7%) и `#session-badge` (`/parse` не возвращает name — бейдж = uuid) |

## 4. Замороженные эталоны

Якоря (REQUIREMENTS §5, MATERIALS_ANALYSIS §8, DECISIONS_LOG):

| Фикстура | Замороженные ожидания |
| -------- | --------------------- |
| Эталонная сеть 6×5, µ=(7,4,2,5,4,3) | 1503/4983; per-place [10,8,16,29,8,10], k=29, bounded; не safe; 23 тупика (порядок D-022); нет мёртвых; все t1–t5 L1 → сеть L1; home=false; тупиковая (DAG, D-035); µ0: разрешены t1–t5; t1 → (5,5,2,5,4,3); **не консервативная (P0#1, FR-606)** |
| PN-04 (5×4, µ=(1,1,0,0,0)) | 5 маркировок, цикл из 4; живая L4; k=1 safe; не консервативная (суммы 2,1,2,2,2) — D-056 |
| PN-05 (решатель) | разрешены t1–t5; цепочка → (5,3,4,6,3,3); v(σ)=(1,1,1,1,1), µ′ совпадает |
| PN-02 | µ*=(1,2,1,0,0); достроенные t3/t4; цикл (t1,t3,t2,t4)×3 |
| PN-07 | µmin=(2,2,0); параллельный (3,3,0) → (0,0,2) |
| PN-08 | coverability, t1 L1, вердикт None, ω-заметка |
| PN-17/18/35 | W−/W+ 1-в-1 (PN-17: failed_at=4 → (0,0,1); PN-35 → (0,1,3,2)) |
| PN-19 | µmin(σ)=(3,0,4) → (0,5,0); тупиковая |
| PN-21 (5×3, µ=(1,2,1,0,0)) | 4 маркировки; частичнотупиковая L1; k=2; не safe; не консервативна — D-056 |
| PN-28/29/31 | живая; 28: k=1 safe консервативная; 29: k=2 не safe консервативная |
| PN-30 (приоритеты) | a) active=[t1], →(2,0,1,0); b) →(0,0,0,1) |
| PN-15/PN-32 (временные) | периоды 9 / 8 |
| PN-33 (ингибитор) | (2,0,1,0) / (0,0,0,1) |
| PN-36 (цветные) | a=1 → 1; a>1 → true; b=1 → true; b>1 → false; b×c → 3 |
| LSS-01…05 | y(t) в замкнутом виде (LSS-01: 2t²+3t+3√2·cos(t+π/4)−3 и т.д.; LSS-04: t³e^{−t}/6 — кратный корень) |
| LSS-08/09/10 | Φ(s) (1/(s+5) и т.д.) |
| LSS-11/14 | A(ω)=k/√(1+T²ω²), φ(ω)=−atan(Tω); LSS-14a: y_ч=(cos3t−18sin3t)/65 |
| LSS-15/16 | LSS-15b: e^{−7t}/13+12e^{−t/2}/13 |
| LSS-22 | c1x1+c2x2=y0; −c2(a0/a2)x1+(c1−c2(a1/a2))x2=y0′ |
| LSS-23 | W=1/(s+1) + заметка (s+2)/(s²+3s+2); СЛАУ источника несовместна |
| FA-01…08 | такты/состояния/выходные слова по §8; normalize — все три способа; to_mealy — эквивалентность |
| **KaTeX render digest (FR-605/NFR-110)** | `docs/acceptance/math/katex_render_digest.json`: **166/166 строк отрендерено (83 уникальные)**, 0 failed, 0 warnings; источник — все ASCII-формульные строки `answer`+`solution[].data` (LSS-01…23, `*_tex` исключены), KaTeX 0.19.0 (node-рендерер, `audit/katex_digest.py`); эталоны `*_tex`: LSS-08 `\frac{1}{s + 5}`, LSS-23 `\frac{1}{s + 1}`, LSS-14 roots {3−i:1, 3+i:1} |
| **WCAG-контраст тем (NFR-109)** | `docs/THEME_PLAN.md` §3: 5 effective-тем × 12 пар (fg/bg, muted/bg, accent/bg, node-label/canvas, edge-label/canvas, fg/surface, warning-fg/warning-bg, toast-fg/toast-bg, active-strong/active-fill, current-border/canvas, accent-hover/bg, btn-hover-border/btn-hover-bg) — **все пары проходят AA** (текст ≥ 4.5:1, UI ≥ 3:1); минимум по тексту — tokyo-night 10.59 |
| **Визуальные бэйджи (NFR-109, D-058)** | `docs/acceptance/vr-baseline/`: main-light/dark, report-lss14-light/dark (viewport 1400×900, full page); критерий E2E-12 — < 1% пикселей (Δ яркости > 30) при масках `#canvas-net`/`#session-badge` |

## 5. E2E-сценарии (Playwright, `e2e/test_e2e.py`)

Общие: `http://app:8000`; UI — русский; ожидание — поллинг по DOM (без fixed
sleep; исключение — осознанный settle 500 мс в VR-рендре под одноразовые
таймеры канвасов 150/200 мс). **Каждый сценарий** дополнительно падает, если в
console браузера появилась хоть одна ошибка или warning (NFR-107, конвейер
`page.on("console")` в `conftest.py`). Тема задаётся ДО сценария:
`localStorage["pn-theme"]` + reload (анти-FOUC), `dataset.theme` проверяется.

- **E2E-1** — текстовый ввод + полный анализ: «узлов: 1503, рёбер: 4983»,
  11 узлов сети, свойства (k=29, L1, 23, «нет» мёртвых); скриншот
  `docs/acceptance/e2e-1-analysis.png`.
- **E2E-2** — проигрывание: 5 активных; one-click по t1 → «p1 (5)»/«p2 (5)»;
  «Отмена» → «p1 (7)»; «Срабатывание» → «p1 (5)»; клик по первому шагу
  истории → «p1 (5)»; «Сброс» → история пуста, «p1 (7)».
- **E2E-3** — экспорт: CSV (заголовок `p1,p2,p3,p4,p5,p6`, 1504 строки,
  2-я строка `7,4,2,5,4,3`, без ω) и JSON (k=29, L1, 23 тупика).
- **E2E-4** — JSON-ввод: те же 1503/29/L1/23.
- **E2E-5** — история сессий: список ≥1, клик → восстановление без
  пересчёта (1503 узла, k=29).
- **E2E-6** — «Задание из практикума»: 71 карточка; фильтр «Сети Петри» → 40;
  карточка PN-05 → prefill (initial_marking в JSON); «Решить» → отчёт
  Дано/Найти/Решение/Ответ с итоговой маркировкой (5,3,4,6,3,3); скриншот
  `e2e-6-solve-pn.png`.
- **E2E-7** — FA-03: граф автомата 4 вершины; прохождение слова p1 p2 p2 p1 p2
  (s0 s0 s1 s3 s3 s0): «Показать прохождение» → 1 текущее состояние;
  «Следующий такт»; «Показать весь путь» → 3 посещённых вершины; скриншот
  `e2e-7-fa-graph.png`.
- **E2E-8** — PNG: сеть, граф и «PNG всех» — валидные PNG-файлы
  (магика `\x89PNG`, размер > 1 КБ).
- **E2E-9** — темы (FR-601/602, NFR-109): дефолт light (system в headless),
  переключение select → `dataset.theme`, canvas-инстансы те же
  (`window.Registry.net` identity), `localStorage` обновлён, reload → тема
  сохранена.
- **E2E-10** — KaTeX (FR-603/604, NFR-110): LSS-14 — `.report .katex` на месте,
  `aria-label`/`data-tex` с TeX, «сырая» str-sympy-строка в innerText — 0,
  copy TeX → clipboard === data-tex (или тост при non-secure origin); PN-05 —
  «(5,3,4,6,3,3)» в innerText, ≥ 3 `.katex`.
- **E2E-11** — ключевые TASK в обеих темах (параметризация 3 задачи × 2 темы =
  6 тестов): TASK-PN-05 / TASK-LSS-14 / TASK-FA-03 × light/dark. Тема задаётся
  до сценария (`localStorage` + reload); «Задание из практикума» → карточка →
  «Решить» → `.report` есть; PN-05 — «(5,3,4,6,3,3)» в innerText; LSS-14 —
  `.katex` отрендерен (не fallback); FA-03 — граф автомата 4 вершины
  (`window.Registry.automaton`); dark — `dataset.theme === "dark"` и
  `document.querySelectorAll('.formula__fallback').length === 0`.
- **E2E-12** — visual regression (4 теста: main/отчёт LSS-14 × light/dark):
  скриншот full page → Pillow pixel-diff против `vr-baseline/*.png`: размер
  совпадает, < 1% пикселей отличается > 30 по яркости. Маски (одинаково для
  baseline и current): `#canvas-net` (COSE-layout стартует из случайных
  позиций cytoscore — узлы дрифтуют, ~0.7% пикселей) и `#session-badge`
  (`/parse` не возвращает name → бейдж = uuid сессии). Текущие скриншоты —
  `docs/acceptance/vr-current/`. Бэйджи детерминированы (проверено
  повторными съёмками: 0–13 пикселей).
- **E2E-13** — focus-цикл (NFR-111, быстро): главный экран, Tab×10 — 0
  pageerror; каждая остановка либо `:focus-visible`, либо обход к
  `<body>`/`<html>` (стандартное поведение Chromium: свежий экран имеет
  9 таб-стопов); ≥ 9 остановок с видимым фокусом.

При падении — скриншот в `docs/acceptance/failures/`.

## 6. Входы/выходы

Вход: сборка обоих образов; app healthy (`/healthz` → 200); VR-бэйджи на месте
(`docs/acceptance/vr-baseline/`, иначе — `audit/vr_baseline.py`).

Выход: **pytest ≥ 286** (юнит+property), **ruff чисто**, **mypy strict чисто**,
**e2e 13 сценариев (21 тест) зелёные** + console чистый (NFR-107);
аудиты: **axe — 0 critical/major** (иначе — находка, возврат продуктовой
команде), **perf — бюджеты ADR-0012/NFR-112** (иначе — находка); счётчики/
длительности — в TEST_REPORT; любой красный — воспроизведён канонической
командой; артефакты на месте (`docs/acceptance/{a11y,perf,vr-baseline,
vr-current,math,themes}/`).

## 7. Риски

| Риск | Влияние | Митигция |
| ---- | ------- | -------- |
| 1503 узлов в headless Chromium — медленно | flaky-ождания | поллинг по реальному DOM-состоянию с большими таймаутами |
| Дрейф версии Playwright | несовместимость e2e-контейнера | пин `1.49.1` в `e2e/Dockerfile` |
| npm-зависимости на этапе сборки | сбой сборки | образы на пинах в `package.json`; сборка только в Docker; e2e-инструменты (Pillow 12.3.0, axe-core 4.13.0) — точные пины в `e2e/Dockerfile` |
| sympy-нестабильность формул | «красивость» LSS-ответов | канонизация `sp.simplify`/`cancel`; эталоны зафиксированы строками |
| Console-чек слишком строгий | ложные падения e2e | предупреждения Cytoscape устранены в корне (D-055); чек — требование NFR-107 |
| SQLite накапливает сессии между прогонками | влияние на список сессий | ассерты с допуском (≥1, новые первыми) |
| **clipboard API на non-secure origin (http)** | copy TeX может не сработать через `navigator.clipboard` | execCommand-fallback в Formula.vue (FR-603) + тост; E2E-10 проверяет обе ветки (clipboard === tex ИЛИ тост «TeX скопирован») |
| **axe-core 4.13: impact «major» переименован в «serious»** | критерий NFR-111 («0 major») пропускает находки при наивном подсчёте | `audit/axe_check.py` считает major = {major, serious}; версия axe зафиксирована в `axe_summary.json` |
| **VR-недетерминизм**: COSE-layout сети (случайные начальные позиции) и uuid-бейдж | пиксельный диф main-экрана до ~1% (на границе порога) | маски `#canvas-net`/`#session-badge` (контент канваса покрывается функциональными E2E-1/2/5 и скриншотами тем); бэйджи пересоздаются `audit/vr_baseline.py` |
| **GIL-конкуренция под solve**: CPU-воркер держит GIL (sympy/gmpy), event loop задерживается на интервалы переключения ~5–100 мс | p95 healthz под холодным тяжёлым solve может превышать 50 мс (NFR-112) | замер честный (холодный solve, уникальные ключи кэша, метод audit_extra2); при превышении — находка в TEST_REPORT, не «лечим» порогом |
