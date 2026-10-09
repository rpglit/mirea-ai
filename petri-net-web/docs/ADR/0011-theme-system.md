# ADR-0011: Темы оформления — design tokens, 6 тем, JS-палитры Cytoscape

Status: Принята (09.10.2026, раунд 3)

## Контекст

Итерация 3 (D-058; REQUIREMENTS §7–8: FR-601, FR-602, NFR-109, NFR-111):
темы light/dark/system + именованные (Tokyo Night, Catppuccin Mocha,
Synthwave '84); переключатель в шапке; persistence без FOUC;
WCAG 2.1 AA (текст ≥ 4.5:1, UI-компоненты ≥ 3:1); переключение без перезагрузки
и без re-layout графов; паритет функциональности. Текущий UI — только светлый:
hardcoded hex в `style.css` и в Cytoscape-стилях NetCanvas/ReachabilityCanvas/
AutomatonCanvas (45 ролей токенов — THEME_PLAN §1). Cytoscape рисует на
**canvas** — CSS-переменные внутри canvas-стилей НЕ читаются (тех. заметка
D-058) — темизация графов требует механизма отдельно от CSS. e2e-контракт
морозит идентичность инстансов `window.Registry.{net,graph,automaton}` —
смена темы не должна пересоздавать графы. Детальный план и финальные палитры —
`THEME_PLAN.md` (фаза 1.2).

## Решение

- **Design tokens**: все hex `style.css`/компонентов заменяются CSS-переменными
  `--pn-*` (45: bg/fg/muted, accent(+contrast/+hover), surface(+2),
  border(+strong/+soft), input/canvas-bg, node-*, transition-*, active-*(+strong),
  firing, edge-*, deadlock, current(+border), inhibitor, graph-node-*, table-*,
  warning-*, error, toast-*, formula-*, focus-ring, btn-hover-*). Покрытие 100%
  hex проверено grep'ом (ревью фазы 1). Источник — `frontend/src/theme/tokens.css`:
  `:root[data-theme="…"]` на effective-тему; `style.css` использует только
  `var(--pn-*)` (hex нет) + `focus-visible`-контур `--pn-focus-ring`. Полная
  таблица токенов и текущие значения — THEME_PLAN §1.
- **6 тем**: `light`, `dark`, `system`, `tokyo-night`, `catppuccin-mocha`,
  `synthwave84`. `system` — runtime-выбор:
  `matchMedia("(prefers-color-scheme: dark)")` → `data-theme` ∈ {light, dark,
  tokyo-night, catppuccin-mocha, synthwave84} — в DOM `system` не живёт,
  только как сохранённый выбор. Live-слушатель matchMedia применяет смену
  OS-темы только при `store.theme === "system"`. Финальные палитры (после
  проверки контраста) — THEME_PLAN §2.
- **Persistence + anti-FOUC**: `localStorage["pn-theme"]` (дефолт `system`);
  inline-скрипт в `<head>` `index.html` ПЕРЕД `<script type="module">` (без
  внешних зависимостей): читает localStorage, резолвит `system`, ставит
  `document.documentElement.dataset.theme`; при ошибке — `light`. Страница
  рендерится с итоговой темой с первого кадра (FOUC исключён конструктивно).
- **Переключатель**: `ThemeSwitcher.vue` в шапке `App.vue` (правее view-tabs):
  `<select aria-label="Тема">`, 6 опций на русском («Светлая», «Тёмная»,
  «Системная», «Tokyo Night», «Catppuccin Mocha», «Synthwave '84»);
  focus-visible ring; клавиатура — native select (стрелки/Enter) + hotkey «T»
  (циклическое переключение — FR-615; полный набор hotkeys — вне этой ADR).
- **Единый источник темы**: `store.theme` (reactive) + `applyTheme(theme)` в
  `src/theme/index.js` (пишет localStorage, вычисляет effective, ставит
  `data-theme`). Смена темы не меняет дерево компонентов Vue — только
  CSS-variables (мгновенно) + рестил Cytoscape.
- **Cytoscape — JS-палитры**: `src/theme/palettes.js` — `GRAPH_PALETTES`:
  JS-зеркала графических токенов (canvas-bg, node-fill/border/label,
  transition-*, edge, edge-label(-bg), deadlock, current, firing, inhibitor,
  graph-node-*) на все 5 effective-тем; `style(palette)` канвас-компонентов
  строится из палитры (canvas не читает CSS-переменные — см. контекст).
  Semantic-подсветки (active/deadlock/current/firing/path) — по классам;
  меняются только цвета классов внутри palette-стилей.
- **Рестил без destroy** (открытый вопрос аудита #3 — ответ: **да, совместимо
  с `window.Registry`**): при смене темы — `cy.style(paletteStyles)` на
  СУЩЕСТВУЮЩЕМ инстансе (Cytoscape 3.x принимает полный style-массив как
  замену; на 3.34.3 — проверить в фазе реализации, при необходимости
  `cy.batch(...)`). Инстансы `window.Registry.{net,graph,automaton}`
  СОХРАНЯЮТСЯ (e2e-контракт не нарушается), layout/выбор/zoom не сбрасываются;
  re-layout при смене темы НЕ вызывается. Fallback, если замена стиля в этой
  версии не работает: destroy+rebuild с обновлением записи
  `window.Registry.*` на новый инстанс (Registry остаётся контрактной точкой
  доступа; побочка — layout-«прыжок»; риск 12 ARCH §6).
- **WCAG 2.1 AA** — все пары проходят (relative luminance, скрипт в
  `python:3.12-slim`, 09.10; THEME_PLAN §3):

  | Тема | fg/bg | muted/bg | accent/bg | node-label/canvas | edge-label/canvas | fg/surface | warning-fg/warning-bg | toast-fg/toast-bg |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | light | 15.91 | 7.46 | 5.17 | 21.00 | 15.91 | 14.59 | 6.62 | 12.63 |
  | dark | 14.19 | 6.99 | 7.76 | 18.10 | 13.71 | 12.63 | 10.89 | 14.35 |
  | tokyo-night | 10.59 | 8.10 | 6.79 | 11.14 | 8.52 | 9.02 | 7.03 | 9.02 |
  | catppuccin-mocha | 11.34 | 7.37 | 7.79 | 12.14 | 9.91 | 8.69 | 10.56 | 8.69 |
  | synthwave84 | 15.48 | 9.35 | 6.92 | 17.11 | 10.34 | 13.25 | 10.52 | 13.25 |

  (Пересчёт после ревью фазы 1: warning-fg — против warning-bg, toast-fg —
  против toast-bg; расширенная таблица c semantic-парами — THEME_PLAN §3.)
  Semantic-цвета различимы по hue, а не только по контрасту (паритет).
  Правки до финала (muted tokyo-night/catppuccin/dark/synthwave не проходили
  AA у опорных палитр) — THEME_PLAN §3.
- **Приёмка**: e2e-сценарий **E2E-9** (новый): переключение в «Тёмная» через
  UI → `data-theme === "dark"`, инстанс `window.Registry.net` тот же, стили
  переставлены; «Tokyo Night» → dataset обновлён; reload → тема сохранена
  (localStorage); возврат в «Светлую»; console чистый (NFR-107). Скриншоты
  `docs/acceptance/themes/` (main/report/graph/props × light/dark,
  tokyo-night бонусом). Контраст-функция (luminance/ratio) — чистый модуль с
  юнит-тестами на парах таблицы (если введён vitest; иначе E2E-9 + ручной
  чек).

## Последствия

- Новые модули `src/theme/{tokens.css,palettes.js,index.js}` + компоненты
  `ThemeSwitcher.vue`, `style.css` → токены (дерево — ARCH §3); `store.js` +
  `theme`; канвас-компоненты — `style(palette)` + watcher темы.
- Токены `--pn-formula-bg/-fg` координируются с ADR-0012: `Formula.vue`
  использует только токены (hardcoded-цветов в компоненте нет).
- FOUC исключён конструктивно; тема переживает reload и перезапуск браузера;
  `system` живьём следует за OS-темой.
- В тёмных темах `edge-label-bg` = canvas-bg (плашки подписей дуг сливаются
  с фоном — намеренно, чтобы не плодить прямоугольники; читаемость
  edge-label/canvas — в таблице выше).
- Риск `cy.style()` swap на Cytoscape 3.34.3 — проверка в фазе реализации,
  fallback destroy+rebuild с сохранением Registry (ARCH §6, риск 12).
