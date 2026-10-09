# План тем оформления — petri-net-web (итерация 3)

|        |                                                            |
| ------ | ---------------------------------------------------------- |
| Статус | v1.0, Фаза 1.2                                             |
| Дата   | 2026-10-09                                                 |
| Автор  | ui-theme-agent (план завершён оркестратором — см. D-059)  |

Темы: `light`, `dark`, `system`, `tokyo-night`, `catppuccin-mocha`, `synthwave84`.
Требования: WCAG 2.1 AA (текст ≥ 4.5:1, UI-компоненты ≥ 3:1), отсутствие FOUC,
переключение без перезагрузки и без re-layout графов, паритет функциональности.

## 1. Design tokens

Все hex в `style.css` и Cytoscape-стилях компонентов заменяются токенами.
`frontend/src/theme/tokens.css` — `:root[data-theme="..."] { ... }` на тему.

| Токен | Назначение | Сейчас (file) |
| ----- | ---------- | ------------- |
| `--pn-bg` | фон страницы | `#fff` (style.css) |
| `--pn-fg` | основной текст | `#222` |
| `--pn-muted` | второстепенный текст (мuted-классы, дате, подписи) | `#555`, `#888`, `#777`, `#666` |
| `--pn-accent` | акцент: primary-кнопки, active-табы, ссылки, focus | `#2563eb`, `#1d4ed8` (hover) |
| `--pn-accent-contrast` | текст на акценте | `#fff` |
| `--pn-surface` | фон карточек/панелей/полей | `#f5f5f5`, `#fafbfc`, `#fafafa`, `#f6f8fa` |
| `--pn-surface-2` | приподнятая поверхность (hover-строки, active-карточка) | `#ebebeb`, `#e3f2fd`, `#eff6ff` |
| `--pn-border` | рамки (инпуты, кнопки, панели) | `#ccc`, `#ddd`, `#e0e0e0`, `#e5e5e5`, `#e8e8e8` |
| `--pn-border-strong` | активная рамка (canvas.active-canvas, selected) | `#2563eb` |
| `--pn-input-bg` | фон инпутов/textarea | `#fff` |
| `--pn-canvas-bg` | фон Cytoscape-контейнеров | `#fff` |
| `--pn-node-fill` | fill позиций | `#ffffff` (NetCanvas) |
| `--pn-node-border` | border позиций | `#000000` |
| `--pn-node-label` | текст меток позиций | `#000000` |
| `--pn-transition-fill` | fill переходов | `#e8eef7` |
| `--pn-transition-label` | текст меток переходов | `#000000` |
| `--pn-active-fill` | разрешённые переходы (fill) | `#c8e6c9` |
| `--pn-active-border` | разрешённые переходы (border) | `#2e7d32` |
| `--pn-firing-fill` | пульс срабатывания | `#66bb6a` |
| `--pn-edge` | линии дуг | `#444444`, `#888` (граф) |
| `--pn-edge-label` | текст подписей дуг | `#222222`, `#888` |
| `--pn-edge-label-bg` | фон плашки подписи дуги | `#ffffff` (opacity 0.75) |
| `--pn-deadlock` | тупиковые узлы графа | `#d33` |
| `--pn-current` | текущий узел/акцент выделений | `#1a73e8` (border `#0d47a1`) |
| `--pn-inhibitor` | ингибиторные дуги ⊣ | `#8e24aa` |
| `--pn-graph-node-fill` | узлы графа достижимости | `#eef` |
| `--pn-graph-node-label` | подписи узлов графа | `#333` |
| `--pn-table-header-bg` | шапка таблиц | `#f5f7fa` |
| `--pn-table-border` | рамки таблиц | `#e0e0e0`, `#ddd` |
| `--pn-warning-bg` | caveat/предупреждения (bg) | `#fff3cd` |
| `--pn-warning-border` | (border) | `#ffe08a` |
| `--pn-warning-fg` | текст на warning | `#6b5300` |
| `--pn-error` | ошибки, delete-кнопки | `#b00020` |
| `--pn-toast-bg` | тост (bg) | `#333` |
| `--pn-toast-fg` | тост (текст) | `#fff` |
| `--pn-toast-error-bg` | тост-ошибка | `#b00020` |
| `--pn-formula-bg` | фон формул (KaTeX) | `#f6f8fa` — координировать с math-render-agent |
| `--pn-formula-fg` | цвет формул | `#222` |
| `--pn-focus-ring` | видимый focus (keyboard) | `#2563eb` |
| `--pn-current-border` | border/label текущего узла и start-состояния (доп. к `--pn-current`) | `#0d47a1` |
| `--pn-active-strong` | текст/обводка разрешённых и firing-переходов (на active-fill) | `#1b5e20` |
| `--pn-accent-hover` | hover primary-кнопок/табов | `#1d4ed8` |
| `--pn-btn-hover-bg` | hover кнопки переходов `.btn-transition` | `#e8f5e9` |
| `--pn-btn-hover-border` | border hover-кнопки переходов (≥3:1 к btn-hover-bg) | `#2e7d32` |
| `--pn-border-soft` | мягкие разделители (строки сессий и т.п.) | `#eee` |

Всего токенов: **45** (39 базовых + 6 добавлено по ревью фазы 1 —
покрывают ВСЕ hex из `style.css` и Cytoscape-стилей, включая `#1b5e20`,
`#0d47a1`, `#eee`, `#e8f5e9`/`#4caf50`, `#1d4ed8`).

## 2. Палитры (итоговые, после проверки контраста)

### light
`--pn-bg:#ffffff` `--pn-fg:#222222` `--pn-muted:#555555` `--pn-accent:#2563eb` `--pn-accent-contrast:#ffffff` `--pn-surface:#f5f5f5` `--pn-surface-2:#e3f2fd` `--pn-border:#cccccc` `--pn-border-strong:#2563eb` `--pn-input-bg:#ffffff` `--pn-canvas-bg:#ffffff` `--pn-node-fill:#ffffff` `--pn-node-border:#000000` `--pn-node-label:#000000` `--pn-transition-fill:#e8eef7` `--pn-transition-label:#000000` `--pn-active-fill:#c8e6c9` `--pn-active-border:#2e7d32` `--pn-firing-fill:#66bb6a` `--pn-edge:#444444` `--pn-edge-label:#222222` `--pn-edge-label-bg:#ffffff` `--pn-deadlock:#dd3333` `--pn-current:#1a73e8` `--pn-inhibitor:#8e24aa` `--pn-graph-node-fill:#e8edfb` `--pn-graph-node-label:#333333` `--pn-table-header-bg:#f5f7fa` `--pn-table-border:#e0e0e0` `--pn-warning-bg:#fff3cd` `--pn-warning-border:#ffe08a` `--pn-warning-fg:#6b5300` `--pn-error:#b00020` `--pn-toast-bg:#333333` `--pn-toast-fg:#ffffff` `--pn-toast-error-bg:#b00020` `--pn-formula-bg:#f6f8fa` `--pn-formula-fg:#222222` `--pn-focus-ring:#2563eb` `--pn-current-border:#0d47a1` `--pn-active-strong:#1b5e20` `--pn-accent-hover:#1d4ed8` `--pn-btn-hover-bg:#e8f5e9` `--pn-btn-hover-border:#2e7d32` `--pn-border-soft:#eeeeee`

### dark
`--pn-bg:#121212` `--pn-fg:#e0e0e0` `--pn-muted:#9e9e9e` `--pn-accent:#6ea8fe` `--pn-accent-contrast:#082149` `--pn-surface:#1e1e1e` `--pn-surface-2:#26364a` `--pn-border:#3a3a3a` `--pn-border-strong:#6ea8fe` `--pn-input-bg:#1a1a1a` `--pn-canvas-bg:#161616` `--pn-node-fill:#2a2a2a` `--pn-node-border:#e0e0e0` `--pn-node-label:#ffffff` `--pn-transition-fill:#2b3546` `--pn-transition-label:#e0e0e0` `--pn-active-fill:#1e3a28` `--pn-active-border:#4caf50` `--pn-firing-fill:#66bb6a` `--pn-edge:#9e9e9e` `--pn-edge-label:#e0e0e0` `--pn-edge-label-bg:#161616` `--pn-deadlock:#ef5350` `--pn-current:#6ea8fe` `--pn-inhibitor:#ce93d8` `--pn-graph-node-fill:#2b3546` `--pn-graph-node-label:#e0e0e0` `--pn-table-header-bg:#1e1e1e` `--pn-table-border:#3a3a3a` `--pn-warning-bg:#332b12` `--pn-warning-border:#6b5d2e` `--pn-warning-fg:#ffe08a` `--pn-error:#ef5350` `--pn-toast-bg:#2a2a2a` `--pn-toast-fg:#ffffff` `--pn-toast-error-bg:#c62828` `--pn-formula-bg:#1c1c1c` `--pn-formula-fg:#e0e0e0` `--pn-focus-ring:#6ea8fe` `--pn-current-border:#9ecbff` `--pn-active-strong:#a5d6a7` `--pn-accent-hover:#8ab4f8` `--pn-btn-hover-bg:#1e3a28` `--pn-btn-hover-border:#66bb6a` `--pn-border-soft:#2e2e2e`

### tokyo-night
`--pn-bg:#1a1b26` `--pn-fg:#c0caf5` `--pn-muted:#a9b1d6` `--pn-accent:#7aa2f7` `--pn-accent-contrast:#1a1b26` `--pn-surface:#24283b` `--pn-surface-2:#2c314a` `--pn-border:#3b4261` `--pn-border-strong:#7aa2f7` `--pn-input-bg:#1f2233` `--pn-canvas-bg:#16161e` `--pn-node-fill:#24283b` `--pn-node-border:#c0caf5` `--pn-node-label:#c0caf5` `--pn-transition-fill:#2a2f45` `--pn-transition-label:#c0caf5` `--pn-active-fill:#1f3327` `--pn-active-border:#9ece6a` `--pn-firing-fill:#9ece6a` `--pn-edge:#787c99` `--pn-edge-label:#a9b1d6` `--pn-edge-label-bg:#16161e` `--pn-deadlock:#f7768e` `--pn-current:#7aa2f7` `--pn-inhibitor:#bb9af7` `--pn-graph-node-fill:#2a2f45` `--pn-graph-node-label:#c0caf5` `--pn-table-header-bg:#24283b` `--pn-table-border:#3b4261` `--pn-warning-bg:#322b18` `--pn-warning-border:#5d4d22` `--pn-warning-fg:#e0af68` `--pn-error:#f7768e` `--pn-toast-bg:#24283b` `--pn-toast-fg:#c0caf5` `--pn-toast-error-bg:#f7768e` `--pn-formula-bg:#20222f` `--pn-formula-fg:#c0caf5` `--pn-focus-ring:#7aa2f7` `--pn-current-border:#99c1f1` `--pn-active-strong:#b9e88f` `--pn-accent-hover:#98b8f9` `--pn-btn-hover-bg:#1f3327` `--pn-btn-hover-border:#9ece6a` `--pn-border-soft:#2b3047`

### catppuccin-mocha
`--pn-bg:#1e1e2e` `--pn-fg:#cdd6f4` `--pn-muted:#a6adc8` `--pn-accent:#89b4fa` `--pn-accent-contrast:#1e1e2e` `--pn-surface:#313244` `--pn-surface-2:#3b3d55` `--pn-border:#45475a` `--pn-border-strong:#89b4fa` `--pn-input-bg:#2a2b3d` `--pn-canvas-bg:#181825` `--pn-node-fill:#313244` `--pn-node-border:#cdd6f4` `--pn-node-label:#cdd6f4` `--pn-transition-fill:#3b3d55` `--pn-transition-label:#cdd6f4` `--pn-active-fill:#20362a` `--pn-active-border:#a6e3a1` `--pn-firing-fill:#a6e3a1` `--pn-edge:#7f849c` `--pn-edge-label:#bac2de` `--pn-edge-label-bg:#181825` `--pn-deadlock:#f38ba8` `--pn-current:#89b4fa` `--pn-inhibitor:#cba6f7` `--pn-graph-node-fill:#3b3d55` `--pn-graph-node-label:#cdd6f4` `--pn-table-header-bg:#313244` `--pn-table-border:#45475a` `--pn-warning-bg:#332f1d` `--pn-warning-border:#5d5433` `--pn-warning-fg:#f9e2af` `--pn-error:#f38ba8` `--pn-toast-bg:#313244` `--pn-toast-fg:#cdd6f4` `--pn-toast-error-bg:#f38ba8` `--pn-formula-bg:#2a2b3d` `--pn-formula-fg:#cdd6f4` `--pn-focus-ring:#89b4fa` `--pn-current-border:#aecbff` `--pn-active-strong:#b7efc0` `--pn-accent-hover:#a6c8ff` `--pn-btn-hover-bg:#20362a` `--pn-btn-hover-border:#a6e3a1` `--pn-border-soft:#3b3d55`

### synthwave84
`--pn-bg:#241b2f` `--pn-fg:#f8f8f2` `--pn-muted:#c2bdf6` `--pn-accent:#ff79c6` `--pn-accent-contrast:#241b2f` `--pn-surface:#342446` `--pn-surface-2:#402c52` `--pn-border:#4a3861` `--pn-border-strong:#ff79c6` `--pn-input-bg:#2d2138` `--pn-canvas-bg:#1a1220` `--pn-node-fill:#342446` `--pn-node-border:#f8f8f2` `--pn-node-label:#f8f8f2` `--pn-transition-fill:#402c52` `--pn-transition-label:#f8f8f2` `--pn-active-fill:#1f3a33` `--pn-active-border:#36f9f6` `--pn-firing-fill:#36f9f6` `--pn-edge:#848bbd` `--pn-edge-label:#c2bdf6` `--pn-edge-label-bg:#1a1220` `--pn-deadlock:#fe4450` `--pn-current:#f97e72` `--pn-inhibitor:#b775d1` `--pn-graph-node-fill:#402c52` `--pn-graph-node-label:#f8f8f2` `--pn-table-header-bg:#342446` `--pn-table-border:#4a3861` `--pn-warning-bg:#38301a` `--pn-warning-border:#5d5124` `--pn-warning-fg:#f2e5d0` `--pn-error:#fe4450` `--pn-toast-bg:#342446` `--pn-toast-fg:#f8f8f2` `--pn-toast-error-bg:#fe4450` `--pn-formula-bg:#2d2138` `--pn-formula-fg:#f8f8f2` `--pn-focus-ring:#ff79c6` `--pn-current-border:#fab1a0` `--pn-active-strong:#8ffcf0` `--pn-accent-hover:#ff9ad1` `--pn-btn-hover-bg:#1f3a33` `--pn-btn-hover-border:#36f9f6` `--pn-border-soft:#402c52`

`system` — runtime-выбор: `matchMedia("(prefers-color-scheme: dark)").matches ? dark : light`
(для `tokyo-night`/`catppuccin-mocha`/`synthwave84` системного варианта нет —
это фиксированные темы).

## 3. Контраст (WCAG 2.1 AA) — итоговая таблица

Рассчитано скриптом (relative luminance, WCAG) в контейнере
`python:3.12-slim`, 2026-10-09; **пересчитано после ревью фазы 1**
(первая версия таблицы считала warning-fg и toast-fg против фона
страницы вместо собственных фонов — 8 ячеек исправлено). Все пары
проходят AA (text ≥ 4.5:1, UI ≥ 3:1):

| Тема | fg/bg | muted/bg | accent/bg | node-label/canvas | edge-label/canvas | fg/surface | warning-fg/warning-bg | toast-fg/toast-bg | active-strong/active-fill | current-border/canvas | accent-hover/bg | btn-hover-border/btn-hover-bg |
| ---- | ----- | -------- | --------- | ----------------- | ----------------- | ---------- | --------------------- | ----------------- | ------------------------- | --------------------- | --------------- | ----------------------------- |
| light | 15.91 | 7.46 | 5.17 | 21.00 | 15.91 | 14.59 | 6.62 | 12.63 | 5.85 | 8.63 | 6.70 | 4.56* |
| dark | 14.19 | 6.99 | 7.76 | 18.10 | 13.71 | 12.63 | 10.89 | 14.35 | 7.56 | 10.72 | 8.89 | 5.25 |
| tokyo-night | 10.59 | 8.10 | 6.79 | 11.14 | 8.52 | 9.02 | 7.03 | 9.02 | 9.61 | 9.64 | 8.59 | 7.36 |
| catppuccin-mocha | 11.34 | 7.37 | 7.79 | 12.14 | 9.91 | 8.69 | 10.56 | 8.69 | 9.94 | 10.69 | 9.63 | 8.70 |
| synthwave84 | 15.48 | 9.35 | 6.92 | 17.11 | 10.34 | 13.25 | 10.52 | 13.25 | 10.14 | 10.30 | 8.48 | 9.37 |

\* light: начальный кандидат `#4caf50` дал 2.47 (< 3.0) → взят `#2e7d32`
(4.56 — проверен тем же скриптом против `#e8f5e9`).

Правки, внесённые до финала (кандидаты опорных палитр не проходили):
- tokyo-night muted: `#565f89` (2.3:1) → `#a9b1d6` (8.10:1);
- catppuccin subtext `#6c7086` (3.2:1) → `#a6adc8` (7.37:1);
- dark muted `#757575` (4.4:1) → `#9e9e9e` (6.99:1);
- synthwave muted `#848bbd` (4.3:1) → `#c2bdf6` (9.35:1) (для текста;
  `#848bbd` остаётся только как цвет линии дуг — не текст);
- light btn-hover-border: `#4caf50` (2.47:1 к hover-bg) → `#2e7d32`.

Semantic-цвета (active/deadlock/current/firing/inhibitor) — различимы в своих
темах по hue, а не только по контрасту (требование паритета).

## 4. Механика

1. **Анти-FOUC**: в `<head>` `frontend/index.html` до `<script type="module">`
   inline-скрипт (без внешних зависимостей):
   ```js
   (function () {
     try {
       var t = localStorage.getItem("pn-theme") || "system";
       var dark = t === "dark" || t === "tokyo-night" || t === "catppuccin-mocha" || t === "synthwave84";
       if (t === "system") dark = matchMedia("(prefers-color-scheme: dark)").matches;
       document.documentElement.dataset.theme = dark ? (t === "system" ? "dark" : t) : (t === "system" ? "light" : "light");
     } catch (e) { document.documentElement.dataset.theme = "light"; }
   })();
   ```
   (Сокращённо: итог — `data-theme` ∈ {light, dark, tokyo-night, catppuccin-mocha, synthwave84};
   `system` в DOM никогда не живёт — только как сохранённый выбор.)
2. **Хранилище**: `localStorage["pn-theme"]` ∈ {light, dark, system, tokyo-night, catppuccin-mocha, synthwave84}; дефолт `system`.
3. **Переключатель**: `ThemeSwitcher.vue` в шапке `App.vue` (правее view-tabs):
   `<select aria-label="Тема">` с 6 опциями («Светлая», «Тёмная», «Системная»,
   «Tokyo Night», «Catppuccin Mocha», «Synthwave '84»); focus-visible ring
   `--pn-focus-ring`; клавиатура: native select (стрелки/Enter) — hotkey «T»
   циклически переключает (зафиксировать в подсказке, см. hotkeys-часть аудита).
4. **Store**: `store.theme` (reactive) + `applyTheme(theme)` в `src/theme/index.js`:
   пишет localStorage, вычисляет effective (light/dark/...), ставит
   `document.documentElement.dataset.theme`. Тема — единый источник для CSS
   (data-theme) и JS-палитр Cytoscape.
5. **System live**: `matchMedia("(prefers-color-scheme: dark)")` listener —
   при смене OS-темы и `store.theme === "system"` — применить новую.
6. **Без ре-ре ndера Vue**: theme не меняет дерево компонентов — только CSS
   variables (мгновенно) + рестил Cytoscape (п.5).

## 5. Темизация Cytoscape

Cytoscape рисует на **canvas** — CSS-переменные внутри его style-объектов
НЕ работают (canvas не читает computed styles). Стратегия:

1. `frontend/src/theme/palettes.js`: `export const GRAPH_PALETTES = { light: {...}, dark: {...}, ... }`
   — JS-зеркала графических токенов (canvas-bg, node-fill/border/label,
   transition-*, edge, edge-label, edge-label-bg, deadlock, current,
   firing, inhibitor, graph-node-*) на все 5 effective-тем.
2. `style()` в NetCanvas/ReachabilityCanvas/AutomatonCanvas становится
   `style(palette)` — функции принимают палитру из `GRAPH_PALETTES[effectiveTheme]`.
3. **Рестил при переключении — без destroy/re-layout**:
   `cy.style(paletteStyles)` (Cytoscape 3.x принимает полный style-массив
   как замену) на существующем инстансе; инстансы `window.Registry.{net,graph,automaton}`
   сохраняются (e2e-контракт), позиции/выбор/zoom не сбрасываются.
   Если версия cytoscape не поддерживает замену без restore —
   `cy.batch(() => { cy.style(...); })`; re-layout в любом случае НЕ вызываем.
4. Watcher: `watch(() => store.theme, restyleAll)` в компонентах канвасов —
   перестил, если канвас смонтирован.
5. Semantic-подсветки (active/deadlock/current/firing/path) — классы не
   трогаем, меняются только цвета классов (внутри palette-стилей).

## 6. Матрица правок (фаза 2.2)

| Файл | Изменение |
| ---- | --------- |
| `frontend/src/theme/tokens.css` | НОВЫЙ: `:root[data-theme=...]` × 5, все токены |
| `frontend/src/theme/palettes.js` | НОВЫЙ: JS-палитры Cytoscape × 5 |
| `frontend/src/theme/index.js` | НОВЫЙ: `applyTheme`, effective-theme, matchMedia listener |
| `frontend/src/components/ThemeSwitcher.vue` | НОВЫЙ: select в шапке |
| `frontend/index.html` | inline anti-FOUC скрипт в `<head>` |
| `frontend/src/style.css` | все hex → `var(--pn-*)`; + focus-visible стили; + `.katex`-перекрытия под токены (согласовать с math-планом) |
| `frontend/src/store.js` | `theme` в store |
| `frontend/src/App.vue` | ThemeSwitcher в шапке; вызов applyTheme при монтировании |
| `NetCanvas.vue` / `ReachabilityCanvas.vue` / `AutomatonCanvas.vue` | `style(palette)` + рестил на тему (без destroy) |
| Остальные компоненты | hex в компонентах есть только в трёх Cytoscape-канвасах (учтено выше); ReportPanel/SolverView — inline-стилей с цветами нет (проверено grep'ом) |
| `e2e/test_e2e.py` + `conftest.py` | E2E-9 (темы) + fixture скриншотов `docs/acceptance/themes/` |
| `backend/tests/` или `frontend` unit | юнит контраст-хелпера (если выносится в общий модуль — из e2e-скрипта) |

## 7. Тесты и приёмка

- **E2E-9** (новый сценарий): открыть `/`; переключить в «Тёмная» через UI →
  `document.documentElement.dataset.theme === "dark"`; canvas-инстансы те же
  (id сравнения `window.Registry.net`), стили переставлены (проверить
  `cy.style()`/computed через evaluate); «Tokyo Night» → dataset обновился;
  reload → тема сохранена (localStorage); вернуть в «Светлая»;
  console чистый (NFR-107, работает штатный конвейер).
- **Скриншоты** `docs/acceptance/themes/` (полные страницы): main-light.png,
  main-dark.png, report-light.png, report-dark.png, graph-light.png,
  graph-dark.png, props-light.png, props-dark.png (+ tokyo-night/dark-пара
  бонусом, если есть время).
- **Юнит**: контраст-функция (relative luminance + ratio) — чистый модуль с
  тестами (парами из §3); `applyTheme`-логика (system→light/dark) — тест
  (jsdom в vitest — только если qa-agent решит ввести vitest; иначе —
  покрытие e2e-9 + ручной чек).
- **Паритет**: проверка, что каждый класс/элемент из матрицы §6 имеет
  стилизацию во всех 5 effective-тем (ревью по diff'у + скриншоты).

## 8. Риски

1. Замена `cy.style()` на новых версиях Cytoscape — проверить на 3.34.3
   (установлена) в фазе 2; fallback — destroy+rebuild с сохранением
   `window.Registry.*` (e2e-риск: layout-«прыжок»).
2. `edge-label-bg` в тёмных темах = canvas-bg — плашки подписей дуг
   сливаются с фоном (так и задумано, чтобы не плодить прямоугольники);
   читаемость проверена ratio edge-label/canvas.
3. Synthwave '84 — высокая насыщенность акцентов; primary-кнопки с текстом
   `#241b2f` на `#ff79c6` — ratio 6.92 (pass), но визуально проверяется
   скриншотами (parite-review).
4. KaTeX-цвета (`--pn-formula-*`) — координировать с math-render-agent
   (план MATH_RENDER_PLAN.md §стиль).
