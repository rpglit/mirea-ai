# MATH_RENDER_PLAN — план LaTeX-рендеринга (итерация 3, фаза 1.3)

Статус: **план + аналитика**. Продукт не изменён, коммитов нет.
Авторы: math-render-agent. Дата: 2026-10-09.

Вся проверка выполнялась в контейнерах (`app` — solvers/sympy, `node:20-alpine` —
katex 0.19.0, `petri-net-web-e2e` — chromium/playwright, innerText-пробы).

---

## 1. Выбор библиотеки и версия KaTeX

- **KaTeX 0.19.0** (актуальная версия по `npm view katex version`, проверено
  2026-10-09 в `node:20-alpine`). MathJax не рассматривается: тяжелее
  (~1 МБ JS против ~273 КБ), асинхронный рендер ломает e2e-тайминги,
  контракту нужен детерминированный `renderToString`.
- **Только npm, без CDN**: `frontend/package.json` →
  `dependencies: { "katex": "0.19.0" }`. Vite собирает JS в бандл,
  `katex.min.css` импортируется в entry (`main.js`), Vite перепишет
  `url(fonts/...)` в ассеты бандла. Оффлайн-гарантия: после сборки приложение
  не обращается в сеть ни за JS, ни за шрифтами (в отличие от CDN-подхода).
- **Дист-состав** (проверено распаковкой):
  - `katex.min.js` — 273 КБ; `katex.mjs` — 603 КБ (ESM; Vite возьмёт его,
    tree-shaking + minify → ориентировочно 250–280 КБ в бандле);
  - `katex.min.css` — 24,8 КБ (измерено);
  - `fonts/` — 60 файлов: 20 woff2 + 20 woff + 20 ttf, всего 1,1 МБ;
    **только woff2 — 296 КБ** (20 файлов: Main-{Regular,Bold,BoldItalic,Italic},
    Math-{Italic,BoldItalic}, AMS, Caligraphic×2, Fraktur×2, SansSerif×3,
    Script, Size1..Size4, Typewriter).
- **Стратегия ассетов**: берём ВСЕ 20 woff2 (подмножество — отклонено, см.
  риски). Браузер тянет из 20 файлов только фактически используемые
  (font-face подгружается по глифам): для нашего контента ~4–6 файлов
  (Main-Regular/Bold/Italic, Math-Italic, Size1/2 для дробей в display) ≈
  50–70 КБ реальной загрузки; остальные 15 файлов «лежат» в бандле.
- **Прирост бандла** (текущий статик: 572 КБ = JS 552 + CSS 8, без gzip):
  - на диске: +~590–610 КБ → **~1,16–1,18 МБ** (всего ассетов);
  - фактическая загрузка при первом open: +~330–370 КБ
    (JS katex ~280 + CSS 28 + ~50–70 КБ шрифтов).
  - gzip не включён в стеке (FastAPI статик) — цифры «как есть».
  - Оценка приемлемая для локального учебного веб-приложения; оффлайн-режим
    приоритетнее размера.
- **Важно**: `contrib/copy-tex` у KaTeX есть, но НЕ используется — контракт
  требует свой UX (hover/focus-кнопка, тост, aria-label с TeX-исходником);
  реализация в `Formula.vue` (~40 строк), без доп. ассетов.
- **Auto-render НЕ используем** (по контракту): только явный
  `katex.renderToString(tex, {displayMode})` на каждую формулу — контроль,
  производительность, предсказуемый DOM для e2e.

### Проверка совместимости sympy→KaTeX (выполнено)

- Собраны ВСЕ sympy-значения-строки из `answer` + `solution[].data` задач
  **LSS-01..23**: **63 уникальные строки-формулы**.
- Прогнаны через `katex.renderToString` (inline + display): **126/126 рендеров
  без ParseError, 0 console.warn / 0 console.error** (node:20-alpine).
  Включая сложные случаи: `\operatorname{atan}_{2}{\left(...\right)}`,
  `\delta^{\left(1\right)}`, `\theta` (Heaviside), `\operatorname{re}/{im}`
  (LSS-10), `\sqrt{T^{2}\left(\xi^{2}-1\right)}` (LSS-20).
- Дополнительно проверены в chromium (playwright): `pmatrix` (матрицы),
  `cases`/`aligned`, `\operatorname{re}`, `\mu^{\prime}`, `w^{-}(t)\le\mu`,
  `\dashv` (⊣) — всё рендерится, console чист.

---

## 2. Компонент `frontend/src/components/Formula.vue`

### Контракт

```
props:
  tex: string          // TeX-исходник (обязателен)
  display: boolean     // false = inline, true = display block (по умолчанию false)
  label: string?       // запасной текст для fallback (по умолчанию — сам tex)
emit: (нет) — копирование инкапсулировано, тост через store.toast()
```

### DOM-структура (фрост e2e-селекторов)

```html
<span class="formula formula--display" role="math"
      aria-label="{tex}" title="{tex}" data-tex="{tex}">
  <span class="formula__katex" aria-hidden="true">{katex.renderToString(...)}</span>
  <button type="button" class="formula__copy" title="Скопировать TeX">⧉</button>
</span>
```

- **Класс `formula` на корне** — обязателен: e2e-контракт морозит селектор
  `.formula` (сейчас он на `<pre>` в ReportPanel). Display-модификатор —
  отдельным классом, не тегом (корень всегда `<span>`, CSS `display:block`).
- **aria-label = TeX-исходник** (контракт: «копирование TeX через aria-label»).
  KaTeX-овы `ariaLabel`-опция НЕ ставит атрибут (проверено: option принимается,
  атрибута нет) — поэтому aria-label ведём сами. MathML-часть внутри KaTeX
  (`katex-mathml` с `<annotation encoding="application/x-tex">`) дополнительно
  даёт скринридерам и текст для innerText (см. §7.3).
- **`aria-hidden="true"` на `formula__katex`** — проверено: НЕ влияет на
  `innerText` (chromium-проба: текст формулы и якоря сохранены при
  aria-hidden-обёртке), т.е. a11y-паттерн совместим с e2e-якорями.
- **`title` = TeX** (контракт: «TeX-исходник в title»).
- **`data-tex`** — сервисный атрибут для e2e-ассертов (E2E-10).

### Рендер и fallback

- `html = katex.renderToString(tex, { displayMode: display, throwOnError: true })`
  внутри `try/catch`.
- При ошибке (ParseError или любое исключение): **fallback = escaped исходник**
  (`<code class="formula__fallback">`) в том же визуальном стиле (фон/рамка
  токенов), НЕ кидаем в приложение, НЕ пишем в console (контракт NFR-107).
  `throwOnError:false` (красный `.katex-error`) не используем — контракт
  требует escaped source.
- `display`-детект: только явный prop (нет автодетекта по содержимому —
  предсказуемость для e2e и перфоманса).

### Копирование TeX

- Кнопка `⧉` (`.formula__copy`): `opacity:0` по умолчанию,
  `opacity:1` на `:hover` и `:focus-within` родителя; `<button>` —
  клавиатурно достижим (Tab), `focus-visible`-контур.
- Логика: `navigator.clipboard.writeText(tex)` → тост «TeX скопирован»;
  catch → скрытый `<textarea>` + `document.execCommand("copy")` → тост;
  catch → тост «Не удалось скопировать TeX» (error).
- Источник копирования — `props.tex` (канонический), не `innerText`.

### Импорт

`main.js`: `import "katex/dist/katex.min.css";` (+ `import { renderToString }
from "katex"` в Formula.vue). Больше katex нигде не импортируется.

---

## 3. Единый визуальный стиль формул

**docs/THEME_PLAN.md на момент анализа ОТСУТСТВУЕТ** — токены предлагаются
в нумерации контракта и **помечены «координировать с theme-agent»**.

### Токены (предложение; стартовые значения = текущий вид `.formula`, style.css:506)

```css
:root {
  --pn-formula-bg: #f6f8fa;        /* сейчас .formula background */
  --pn-formula-fg: inherit;        /* KaTeX наследует color — не зашито */
  --pn-formula-border: #e8e8e8;    /* сейчас .formula border */
  --pn-formula-radius: 4px;
  --pn-formula-padding-inline: 2px 6px;   /* inline */
  --pn-formula-padding-display: 8px 10px; /* display */
  --pn-formula-margin: 6px 0;
}
```

- Тёмная/именные темы: theme-agent переопределяет `--pn-formula-*` на своём
  уровне темы; Formula.vue использует только токены (hardcoded-цветов в
  компоненте нет, кроме `currentColor`).
- **inline**: фон/рамка лёгкие (почти прозрачный акцент), padding 2×6,
  `.katex { font-size: 1.02em }` — формула стоит в строке с текстом
  (ячейки таблиц, значения свойств).
- **display**: блок, `margin: 8px 0`, padding 8×10, фон/рамка как у
  `.formula`, `.katex-display { margin: 0 }` (задефолтованные отступы KaTeX
  убрать), `overflow-x: auto` + `max-width: 100%` — широкие формулы
  (LSS-10 A(ω) с re/im, LSS-14 y(t)) скроллятся горизонтально на узких
  экранах, НЕ ломают layout таблиц (контракт п.5).
- Фallback-код и copy-кнопка — в тех же цветах токенов.
- KaTeX шрифт (woff2) — единый для всех формул; системный monospace
  остаётся только для НЕ-формульных блоков (JSON-данные, prose step-text).

---

## 4. TeX-поля бэкенда (LSS) + клиентский генератор (PN/FA)

### 4.1. Почему LSS — бэкенд, PN/FA — клиент

- LSS: формулы — `str(sympy_expr)`; канонический TeX = `sp.latex(expr)`,
  вычисляется там, где есть сам expr. Пере-`sympify(str)` клиентом —
  уязвимо (дроби `1/2`, `I`, `pi` — неоднозначно).
- PN/FA: значения — чистые списки/числа/идентификаторы (маркировки,
  матрицы W−/W+/W, v(σ), ω-кортежи, φ/ψ-перечисления). TeX строится
  детерминированно из структуры на клиенте — `frontend/src/math/tex.js`
  (чистые функции, юнит-тестируемы), бэкенд не трогаем.

### 4.2. Детерминизм sp.latex (проверено)

- Двойной прогон `solve()` LSS-01: JSON-дамп идентичен (`determinism: True`).
- 63 уникальные строки: `sp.latex` стабильна между прогонами.
- Примеры вывода (сырой str → sp.latex):
  - `s**2 + 1` → `s^{2} + 1`
  - `2*t**2 + 3*t + 3*sqrt(2)*cos(t + pi/4) - 3` →
    `2 t^{2} + 3 t + 3 \sqrt{2} \cos{\left(t + \frac{\pi}{4} \right)} - 3`
  - `atan2(30*omega*(omega**4 + 16*omega**2 + 100), -5*omega**6 - 30*omega**4 + 300*omega**2 + 5000)` →
    `\operatorname{atan}_{2}{\left(30 \omega \left(\omega^{4} + 16 \omega^{2} + 100\right),- 5 \omega^{6} - 30 \omega^{4} + 300 \omega^{2} + 5000 \right)}`
  - `k*DiracDelta(t - tau, 1)` → `k \delta^{\left( 1 \right)}\left( t - \tau \right)`
  - `1/(s + 5)` → `\frac{1}{s + 5}`
- Специфика (не баги, зафиксировано):
  - `sp.latex(sp.I)` = `i` (италик) — корни «3 - I» → `3 - i` (корректно);
  - символ `y0p` (LSS-22, из ключа ics) → `y0p` без штриха — косметика,
    оставляем (вопрос открытый Q2);
  - `DiracDelta`→`\delta`, `Heaviside`→`\theta` — рендерятся (проверено).

### 4.3. Точный список новых ключей `*_tex` (аддитивный дизайн)

Правило: **только НОВЫЕ ключи рядом со старыми**; старые `str()`-значения
не трогаются → все существующие строковые ассерты бэкенда
(`test_solvers_lss.py:23-128`: `a["phi"] == "1/(s + 5)"` и т.п.) и JSON-
регрессия (`test_solvers_init.py:57`, чистый JSON всех 71 задачи) остаются
зелёными. `_jsonify` (report.py:86) строки прозрачно пропускает.

По видам (kind) LSS:

| kind | задачи | новые ключи в `answer` | новые ключи в `solution[].data` |
|---|---|---|---|
| `ode` | LSS-01..05, LSS-14а, LSS-15б | `P_tex, y_h_tex, y_p_tex, y_tex` | `P_tex, roots_tex` (шаг 1), `y_h_tex` (2), `y_p_tex` (3), `y_tex` (4) |
| `impulse` | LSS-06, 07, 15а, 16а, 17, 19, 20 | `g_tex` | `g_tex` (шаги 1–2) |
| `transfer` | LSS-08, 09, 10, 14б, 16б | `phi_tex`[, `A_tex, phi_f_tex`] | `phi_tex` (1)[, `F_iw_tex, A_tex, phi_f_tex` (2)] |
| `link` | LSS-11, 12 | `law_tex, phi_tex`[, `g_tex, A_tex, phi_f_tex`] | то же (step 1 `data` = answer) |
| `links_catalog` | LSS-13 | в строках `links[]`: `law_tex, phi_tex, g_tex` (11 строк) | `data` = те же rows |
| `links_impulse` | LSS-18 | в строках: `g_tex` (6 строк) | то же |
| `statespace` | LSS-21, 22, 23 | `W_tex`[, `x0_equations_tex` (list), `x0_tex` (dict)] | `W_tex` (1); `x0_equations_tex` (2) |
| `parts` | LSS-14, 15, 16 | вложенные `answer["<part>"]` наследуют ключи вида части | шаги ре-нумеруются, data те же |

Дополнительно:
- `given["statement_tex"]` — **23 hand-written TeX** (в `_TASKS` рядом с
  `statement`), напр. LSS-01: `y''(t) + y(t) = 2t^{2} + 3t + 1, \quad
  y(0)=0,\ y'(0)=0,\ y''(0)=1`.
- `LINKS` (links.py): `law_tex` — **11 hand-written TeX**
  (напр. `T y'(t) + y(t) = k x(t)`, `y(t) = \int x(\beta)\,d\beta`).
- Итог: **15 новых distinct-имён ключей**: `P_tex, y_h_tex, y_p_tex, y_tex,
  roots_tex, g_tex, phi_tex, A_tex, phi_f_tex, F_iw_tex, law_tex, W_tex,
  x0_equations_tex, x0_tex` + `given.statement_tex` (row-ключи каталога
  переиспользуют `phi_tex/g_tex/law_tex`), ~90 значений на все задачи;
  `roots_tex` = `{sp.latex(r): m}` (параллельно `roots` = `{str(r): m}`).
- `F/B/C/D` (statespace) — остаются nested lists (`_jsonify`); TeX на клиенте
  через `matrixToTex` (матрицы — чистые числа/символы, пере-sympify не нужен;
  но если в `F` символы (LSS-22: `-a0/a2`) — строки, `matrixToTex`
  экранирует/ставит как есть: `-\frac{a_{0}}{a_{2}}`? Нет — строки из
  `_jsonify` это `str(Rational)` = `-a0/a2`; `matrixToTex` для строковых
  ячеек применяет `fracTex("-a0/a2")` → `\frac{-a0}{a2}` + labelTex для
  идентификаторов. Детали — юнит-тесты §6).

### 4.4. `frontend/src/math/tex.js` (PN/FA + общие)

Чистые функции (без зависимостей от Vue):

| функция | вход → вывод |
|---|---|
| `tupleToTex(vals)` | `[5,3,4,6,3,3]` → `\left(5,3,4,6,3,3\right)` (без пробелов — e2e-якорь E2E-6, §7.3) |
| `markingToTex(vals)` | `[7,4,2,5,null,3]` → `\left(7,4,2,5,\omega,3\right)` (null→`\omega`) |
| `omegaTupleToTex(vals)` | алиас `markingToTex` (номенклатура контракта) |
| `matrixToTex(nested)` | `[[1,0],[0,1],[1,1]]` → `\begin{pmatrix}1&0\\0&1\\1&1\end{pmatrix}` (рендер pmatrix проверен в chromium) |
| `ioMatrixToTex(nested, rowLabels, colLabels)` | W− 3×2 + p/t → `\begin{array}{c|cc} & t_1 & t_2 \\ \hline p_1 & 1 & 0 \\ p_2 & 0 & 1 \\ p_3 & 1 & 1 \end{array}` (array+`\hline` в KaTeX поддерживается — проверить в фазе 2) |
| `sigmaToTex(seq)` | `["t1","t2"]` → `(t_1, t_2)` через `labelTex` |
| `labelTex(name)` | `p1` → `p_1`; `t12` → `t_{12}`; `a` → `a` (regex `^([a-zA-Z]+)(\d+)$`) |
| `faEnumToTex(line)` | `s0 = φ(s0, p1)` → `s_0 = \varphi(s_0, p_1)`; `w1 = ψ(s1)` → `w_1 = \psi(s_1)`; несовпало → null (caller оставит plain) |
| `fracTex(str)` | `"-a0/a2"` (строка из _jsonify) → `- \frac{a_0}{a_2}` (для символьных ячеек F) |

Правило разграничения (важно для e2e): **идентификаторы-слова
(состояния `s0`, переходы `t1`, выходы `w0`, позиции `p1`) в СПИСКАХ и
ПРОЗЕ остаются обычным текстом**; Formula получают только формульные
значения: функции/выражения (LSS `*_tex`), маркировки/кортежи чисел,
матрицы, уравнения, φ/ψ-перечисления.

---

## 5. Полная карта «мест с математикой» и точки интеграции

Легенда: **F-инлайн** / **F-дисплей** = Formula inline/display; **plain** =
остаётся обычным текстом (решение зафиксировано).

### 5.1. ReportPanel.vue (frontend/src/components/ReportPanel.vue)

| # | поле / ветка шаблона | file:line | пример «сырой» строки (реальный, из контейнера) | тип обозначения | новое | данные для TeX |
|---|---|---|---|---|---|---|
| 1 | given: строка (statement) | 172–174 | `y'' + y = 2t² + 3t + 1, y(0) = 0, y'(0) = 0, y''(0) = 1.` (LSS-01) | ОДУ (заявление) | **F-дисплей** (LSS), plain (PN/FA) | `given.statement_tex` (бэкенд, 23 шт.) |
| 2 | given: объект (spec/net/input) | 175–177 | `{"a": [1,0,1], "rhs": [{"type": "poly", ...}]}` | конфиг (не математика) | plain `<pre class="formula">` | — |
| 3 | find[] | 185 | `A(ω) = k/√(1+T²ω²)` (LSS-11) | A(ω) (названия) | plain (список «что найти») | — |
| 4 | solution[].text (prose) | 193 | `P(s) = s**2 - 6*s + 10; корни: 3 - I (кратность 1)` (LSS-14) / `y_о(t) = C_1*cos(t) + C_2*sin(t)` | ODU, P(λ), корни, y(t) | `<pre class="step-text">` остаётся; **встроенные сырые формулы заменяются инлайн-Formula** по карте raw→tex (см. ниже) | из `solution[].data` / `answer` (`*_tex`-спутники) |
| 5 | solution data: таблица cols/rows | 196–211 | FA-02: `s0/w0 \| s0 \| s1` | таблицы переходов | plain (идентификаторы) | — |
| 6 | answer.links (каталог LSS-13/18; solution data-массив в ветке 212–234 не рендерится) | 307–316 | сейчас — JSON-строки ячеек (`cellText` → `JSON.stringify(row)`) | Φ(s), g(t,τ), законы звеньев | **новая нормальная таблица** (cols: звено/закон/Φ(s)/g(t,τ)) — см. Q3 | `phi_tex, g_tex, law_tex` (бэкенд, в строках) |
| 7 | solution data: скаляры/строки (P, roots, y_h, y_p, y, g, phi, F_iw, A, phi_f, W, x0_equations) | 225–232 | `1/(s + 5)` (LSS-08); `-5/(omega**2 + 6*I*omega - 10)` (F_iw, LSS-14); `Eq(2*x1 + x2, 1)` (LSS-23) | Φ(s), y(t), Φ(iω), A(ω), φ(ω), W(s), (sE−F)⁻¹, СЛАУ X(0) | **F-дисплей** (уравнения — по одному display) | `*_tex` из data (бэкенд) |
| 8 | answer: строки | 247–249 | `(122*sin(t) - cos(t))*exp(3*t)/65 - 18*sin(3*t)/65 + cos(3*t)/65` (LSS-14 y); `(c1 + c2*s)/(a0 + a1*s + a2*s**2)` (LSS-22 W) | y(t), Φ(s), A(ω)/φ(ω), W(s), g(t,τ), P(λ) | **F-дисплей** | `answer.*_tex` (бэкенд) |
| 9 | answer: список скаляров (tupleText) | 295 | `[5,3,4,6,3,3]` → `(5,3,4,6,3,3)` (PN-05 final_marking); `[7,4,2,5,4,3]` (mu0); `["s0","s0","s1","s3","s3","s0"]` (FA-03 states) | µ-векторы, ω-маркировки / идентификаторы | маркировки (числа/null) — **F-инлайн** `tupleToTex/markingToTex`; списки идентификаторов (states, output_word) — **plain** | клиент-генератор |
| 10 | answer: список кортежей (таблица) | 296–306 | PN-03 deadlocks: `[[3,4,2,5,4,3],[2,5,2,5,4,3]]` (ω: null-компоненты) | ω-маркировки | **F-инлайн** `markingToTex` в ячейках | клиент-генератор |
| 11 | answer: объекты (матрицы, x0, parts) | 307–316 | PN-17 `W_minus=[[1,0],[0,1],[1,1]]`; LSS-23 `x0={x1: "(-a1*c2*y0 + ...)/..."}` | I/O-матрицы, F,B,C,D, X(0), (sE−F)⁻¹ | матрицы — **F-дисплей** `matrixToTex/ioMatrixToTex`; x0 — **F-дисплей** `x0_tex`; parts-вложенные — рекурсивно как 8–11 | бэкенд (`W_tex, x0_tex`) + клиент (матрицы) |
| 12 | answer: mealy/normalize enumeration (pre) | 271–273 | `s0 = φ(s0, p1)` … `w1 = ψ(s1)` | (φ, ψ) | **F-дисплей** построчно `faEnumToTex` (несовпало → plain строка) | клиент-генератор |
| 13 | answer: fa/mealy table | 254–269, 274–287 | `s0/w0` | таблицы переходов | plain (идентификаторы) | — |
| 14 | notes[] | 343 | `однородное решение C·e^{−(a0/a1)·t}, вариация постоянной: ...` (LSS-06) | g(t,τ) в прозе | plain (проза) | — |
| 15 | ANSWER_LABELS (answer-key) | 11–44, 246 | `µ′ = µ + W·v(σ)`, `y(t) = y_о(t) + y_ч(t)` | метки-подписи | plain (заголовки строк ответа) | — |

**Механизм п.4 (step.text):** фронт строит карту `raw→tex` из `answer`
(рекурсивно, включая `parts`-под-объекты LSS-14/15/16) и всех
`solution[].data` (любая пара ключей `X`/`X_tex` + `roots`/`roots_tex`),
заменяет в тексте вхождения raw-строк (sort по длине ↓, `split().join()` —
без regex) на `<Formula :tex>`. Детерминизм гарантирован: бэкенд собирает
текст f-строками из тех же str-значений, что кладёт в data/answer.
Остаточные prose-фрагменты вне карты (напр. `e^{st}`, `s^i` в LSS-14 step 5)
остаются plain — зафиксировано как приемлемо (Q5).

### 5.2. PropertiesPanel.vue (frontend/src/components/PropertiesPanel.vue)

| # | строка таблицы | file:line | пример значения | тип | новое | e2e-якорь |
|---|---|---|---|---|---|---|
| 16 | k-ограниченная | 38–41 | `k = 29` / `неограничена (k = ω)` | k/ω | **F-инлайн** `k = 29` (tex `k = 29`); unbounded — `k = \omega` | **E2E-1/4/5 «29»** — сохранён (проба §7.3) |
| 17 | Ограниченность по позициям | 49–55 | `p1 ≤ 5, p2 ≤ 29, p3 ≤ 5, ...` | per-place k | **F-инлайн** на сегмент `p_1 \le 5` (plain запятая между) | — |
| 18 | Безопасная | 62 | `да (k = 1)` / `нет` | k | «нет» plain; «да (k = 1)» → **F-инлайн** `k = 1` | E2E-1 «нет» — plain ✓ |
| 19 | Тупики | 75–77 | `23: (7,4,2,5,4,3), (3,4,2,5,4,3), ...` | ω-маркировки | счёт `23:` plain; каждый кортеж — **F-инлайн** `markingToTex` | E2E-1/4 «23» — plain ✓ |
| 20 | Минимальная маркировка µmin | 132–134 | `(7,2,2,2,2,2)` | µ-вектор | **F-инлайн** `markingToTex` | — |
| 21 | Живость (verdict/level/по переходам), Маркировок/рёбер, Консервативная, Обратимость | 22–43, 94–119, 121–128 | `L1`, `t1: L4 (возникает); t2: L4 (...)`, `1503 / 4983` | L-шкала, идентификаторы | **plain** (уровни L0–L4 и t-идентификаторы — не формулы) | **E2E-1/4 «L1»** — plain ✓ |
| 22 | Пояснение (note) | 163, 42–99 | `...не превышает некоторое целое k` | проза | plain | — |
| 23 | caveat (ω-приближение) | 145–150 | `Дискретная (ω) приближённая оценка — сеть неограниченна` | ω в слове | plain (Unicode ω) | id `#props-caveat` не трогаем |

### 5.3. Остальные компоненты (решения: НЕ рендерим)

| # | место | file:line | пример | почему plain |
|---|---|---|---|---|
| 24 | StepPanel history-line | StepPanel.vue:12–18 | `(7,4,2,5,4,3) → (5,5,2,5,4,3) (t1)` | операционная панель проигрывания; рядом e2e E2E-2 (клик-цели) |
| 25 | StepPanel кнопки переходов | StepPanel.vue:36–46 | `t1` | идентификаторы; `#active-list` заморожен |
| 26 | NetCanvas place label | NetCanvas.vue:19–21 | `p1 (5)` | **e2e E2E-2 замороженный якорь** (`wait_net_label`); SVG, HTML невозможен |
| 27 | NetCanvas edge label | NetCanvas.vue:23–28 | `2 τ4` | SVG-текст; Unicode τ читаем; tooltip/caption ниже |
| 28 | NetView canvas-caption ⊣ | NetView.vue:310–312 | `(⊣ — ингибиторная дуга)` | Unicode ⊣/τ — не «сырая ASCII-математика» |
| 29 | NetView queryResult | NetView.vue:215 | `не определено (ω)` | одно слово + ω |
| 30 | NetView graph-stats | (текст) | `узлов: 1503, рёбер: 4983` | **якорь `wait_analysis`** (conftest.py:91) |
| 31 | InputTabs textarea#input-text | InputTabs.vue:191–192, store.js:6–13 | `S = (P, T, I, O, µ), ... µ = (7, 4, 2, 5, 4, 3).` | **входной текст парсера** — рендер невозможен |
| 32 | InputTabs form (плейсхолдеры, τ-лейблы, ⊣-опция) | InputTabs.vue:218–267 | `7, 4, 2, 5, 4, 3`; `Задержки τ`; `ингибитор (⊣, ...)` | input/placeholder — не вывод |
| 33 | TaskPicker карточки / SolverView h3 | TaskPicker.vue:60, SolverView.vue:109 | `Выходной сигнал y(t): ОДУ №1 (y″+y = 2t²+3t+1)` | 71 карточка × KaTeX — перфоманс; заголовки |
| 34 | store.prettyFormula | store.js:70–76 | `2*t**2` → `2·t^2` | остаётся как fallback для строк без `*_tex` |
| 35 | store.compactTuple | store.js:55–59 | `7,4,2,5,4,3` (null→ω) | остаётся (текстовый формат); tex-параллель — `markingToTex` |

**Итого**: 35 аудит-мест; в Formula конвертируется **14** (ReportPanel: 1, 4,
6, 7, 8, 9, 10, 11, 12; PropertiesPanel: 16, 17, 18, 19, 20); 21 остаётся
plain по зафиксированным причинам (включая все e2e-якоря).

---

## 6. План тестов

### 6.1. Бэкенд (в контейнере `app`, гейт `ruff+mypy+pytest`, 264 → +N)

Новые тесты в `backend/tests/test_solvers_lss_tex.py` (отдельный файл, старые
не трогаем):
- для представителя каждого kind: `LSS-01` (ode), `LSS-06` (impulse),
  `LSS-08` (transfer), `LSS-10` (freq), `LSS-11` (link), `LSS-13` (catalog),
  `LSS-18` (links_impulse), `LSS-22` (statespace+ics), `LSS-14` (parts):
  - presence: все `*_tex` ключи на месте (answer + data);
  - exact: `answer["phi_tex"] == sp.latex(sp.sympify(answer["phi"]))`
    (детерминизм) + 2–3 жёстких эталонные строки
    (`LSS-08: "\\frac{1}{s + 5}"`, `LSS-23 W_tex: "\\frac{1}{s + 1}"`);
  - `roots_tex` LSS-14: `{"3 - i": 1, "3 + i": 1}`;
  - старые ключи не изменились (дублирует существующие ассерты, но
    зафиксировано рядом);
  - `statement_tex` присутствует во всех 23 LSS-задачах и **рендерится**
    проверкой: строка содержит `\\` и не содержит ASCII `**` (лёгкий
    smoke; полный рендер — e2e).
- Итог: ~15–20 новых assert-групп; все 264 старых — без изменений.

### 6.2. Фронтенд-юнит (vitest — новый devDependency + runner)

`frontend/package.json`: `+ devDependencies: { "vitest": "^3", "@vue/test-utils": "^2" }`,
`scripts: { "test": "vitest run" }`. Запуск без host-инсталла (правило):
`sudo docker run --rm -v $PWD/frontend:/app -w /app node:20-alpine sh -c
"npm install --no-audit --no-fund && npm test"` (или новый compose-сервис
`ftest` на node:20-alpine — решение в фазе 2).

- `frontend/src/math/tex.js` (`tests/tex.spec.js`, ~15 кейсов):
  - `tupleToTex`: числа, пустой список, отрицательные;
  - `markingToTex/omegaTupleToTex`: null → `\omega`, смешанные;
  - `matrixToTex`: 2×2, 3×1, 1×3, пустая матрица (degenerate);
  - `ioMatrixToTex`: с лейблами p1/t12 (labelTex), без;
  - `labelTex`: `p1`→`p_1`, `t12`→`t_{12}`, `a`→`a`, `p12x`→как есть;
  - `sigmaToTex`: `["t1","t2"]` → `(t_1, t_2)`;
  - `faEnumToTex`: φ-строка, ψ-строка, mealy-ψ со вторым аргументом,
    несовпадение → null;
  - `fracTex`: `"-a0/a2"`, `"1/2"`, строка без дроби → как есть.
- `Formula.vue` (`tests/Formula.spec.js`, jsdom):
  - валидный tex → `.katex` в DOM; display → класс `formula--display`;
  - **кривой TeX** `\frac{1}{` → `.formula__fallback` с escaped-исходником,
    исключение не пробито, console.error не вызван (spy);
  - `aria-label === tex`, `title === tex`, `data-tex === tex`;
  - клик copy → `navigator.clipboard.writeText` (mock) вызван с tex + тост;
    clipboard отклонён → execCommand fallback (mock); оба упали → error-тост;
  - класс `formula` всегда на корне (фрост селекторов).
- `ReportPanel.vue` (smoke-монтаж): фикстур-отчёт LSS-08 (phi + phi_tex) →
  `.report .katex` присутствует; фикстур PN-05 (final_marking) →
  `innerText`-эквивалент содержит `(5,3,4,6,3,3)` (jsdom textContent).

### 6.3. E2E (Playwright, контейнер `e2e`)

**E2E-10 (math)** — новый сценарий в `e2e/test_e2e.py`:
1. Открыть **LSS-14** (catalog → «Линейные системы» → TASK-LSS-14 → Решить):
   - `wait_for_selector(".report .katex")`;
   - assert `page.locator(".report .formula").count() >= 6`
     (y, P, phi, A, phi_f, F_iw);
   - assert aria-label содержит TeX: `page.evaluate("() => [...document.querySelectorAll('.report .formula')].some(e => (e.getAttribute('aria-label')||'').includes('frac'))")`
     (CSS-селектор по `aria-label*="\\frac"` не использовать — `\f` в CSS-escape
     это form-feed; проверяем через evaluate);
   - **copy TeX**: на формуле `phi` (`.answer-block .formula[data-tex]`)
     кликнуть `.formula__copy` → `await page.evaluate("navigator.clipboard.readText()")`
     содержит `\frac` (права `clipboard-read/write` — новый локальный
     fixture в conftest, существующий `page`-fixture не трогаем);
   - assert тост «TeX скопирован» в DOM.
2. Открыть **PN-05**:
   - assert `"(5,3,4,6,3,3)" in page.inner_text(".report")` (регрессия якоря E2E-6
     при Formula-рендеринге);
   - assert `.report .katex` ≥ 3 (mu0, chain-final, mu).
3. Скриншоты → `docs/acceptance/math/`:
   - `math-lss14-report.png` (formula-rich отчёт),
   - `math-pn05-report.png`,
   - `math-props-panel.png` (PropertiesPanel с k=29/тупиками/µmin),
   - (после theme-agent: тёмная тема — его скриншоты).
4. Console-чистота E2E-10 — автоматически по NFR-107 (conftest `page`-fixture).

Существующие E2E-1..E2E-8 — **без изменений** (см. §7.3: 0 ассертов требует
обновления).

---

## 7. Риски

### 7.1. Размер бандла

- Сейчас: 572 КБ статик (без gzip). Прирост: **~590–610 КБ на диске**
  (katex JS ~273 КБ ESM-min + CSS 24,8 КБ + 20×woff2 296 КБ) → **~1,16–1,18 МБ**;
  фактическая загрузка первого экрана +~330–370 КБ (шрифты ленивые, ~4–6 файлов).
- Митигация отклонена: сабсет шрифтов (патч katex.min.css) ломает обновления
  KaTeX и экономит только «на диске», не в загрузке.
- Контроль: после сборки в фазе 2 сверить `du -sk static` и список
  `assets/*.woff2` (должно быть ровно 20).

### 7.2. Детерминизм sp.latex

- Проверено: двойной прогон идентичен (LSS-01); 63 уникальные строки стабильны.
- Примеры выводов — §4.2 (3 шт.) + `I`→`i`, `y0p`→`y0p` (косметика, Q2).
- Риск: будущие изменения sympy в Dockerfile (версия зафиксирована в
  pyproject) могут поменять формат latex → тесты с эталонными строками
  (§6.1) это поймают.

### 7.3. E2E-контракт: поассертный анализ (ключевая часть плана)

 Механика (проверено в chromium/playwright, katex 0.19.0): `innerText`
 KaTeX-элемента = **MathML-часть** (Unicode-математика, `\n` между многими
 элементами) **+ HTML-часть** (рядом, без `\n` для простых токенов);
 `aria-hidden` на обёртке innerText НЕ скрывает; `<annotation>` (сырой TeX)
 в innerText НЕ входит.

 **Находка ревью (фаза 1):** содержимое sub/sup НЕ даёт сплошного ASCII в
 `innerText` — прогон: `s_0 = \varphi(s_0, p_1)` →
 `"s\n0\n\t​\n\n=φ(s…"` (ZWSP + таб). Правило для E2E-10 и будущих
 ассертов: НЕ целиться в sub/sup-идентификаторы внутри `.formula`
 (проверять либо plain-секции, либо `data-tex`/aria-label через
 `page.evaluate`). Действующие e2e-ассерты в sub/sup не целятся —
 переписывание не требуется (таблица ниже).

| e2e-ассерт | где | строка/якорь | чувствителен? | решение |
|---|---|---|---|---|
| E2E-1/4/5 `props_text` | #props | `"29" in props` | **частично** — значение `k = 29` станет Formula | якорь жив: MathML-часть даёт «29» (проба a1: `innerText = '𝑘\n=\n29\nk=29'`); **ассерт не меняется** |
| E2E-1/4 `props_text` | #props | `"L1" in props` | нет | уровень живости — plain (решение п.21) |
| E2E-1/4 `props_text` | #props | `"23" in props` | нет | счёт тупиков plain (п.19) |
| E2E-1 `props_text` | #props | `"нет" in props` | нет | «Безопасная: нет» plain (п.18) |
| E2E-2 `wait_net_label`/`net_labels` | SVG NetCanvas | `"p1 (5)"`, `"p1 (7)"`, `"p2 (5)"` | **нет** | place labels НЕ трогаем (п.26) |
| E2E-3 export | download | CSV/JSON | нет | DOM-текст не участвует |
| E2E-6 `inner_text(".report")` | PN-05 | `"Дано"/"Найти"/"Решение"/"Ответ"` | нет | заголовки plain |
| E2E-6 `inner_text(".report")` | PN-05 | `"(5,3,4,6,3,3)" in report_text` | **частично** — final_marking станет Formula | якорь жив: HTML-часть KaTeX для кортежа без пробелов **сплошная** (пробы a4/a10: `'(5,3,4,6,3,3)'`); tex генерируем БЕЗ пробелов; **ассерт не меняется** |
| E2E-7 `inner_text(".report")` | FA-03 | `"w0" in report_text`, `"s3" in report_text` | **нет** (при решении §5) | states/output_word/step.text/таблицы тактов — plain (идентификаторы, п.9/5/13) |
| E2E-7 `Registry.automaton` | SVG | 4 вершины, path-классы | нет | AutomatonCanvas не трогаем |
| E2E-8 export PNG | download | PNG-magic | нет | — |
| `wait_analysis` (conftest.py:79–96, якорь строки 91) | #graph-stats | `"узлов: " + count` | нет | graph-stats plain (п.30) |
| NFR-107 console | все | 0 error/warning | **да — главный риск** | см. 7.4 |
| Фрост селекторов | — | `#props`, `.report`, `.formula`, `.step-text`, `.task-card`, `window.Registry.*` | **да** | корень Formula = `class="formula"`; `<pre class="step-text">` сохранён; `#props`/`.report`/`.task-card`/Registry — без изменений |

**Вывод: 0 существующих e2e-ассертов требуют переписывания.** Якорные
значения («29», «L1», «23», «нет», «(5,3,4,6,3,3)», «w0», «s3», «p1 (5)»,
«узлов: 1503») остаются видимыми в DOM-тексте: либо plain (решения §5),
либо через MathML/HTML-части KaTeX (эмпирически проверено). Страховка:
E2E-10 дублирует проверку `(5,3,4,6,3,3)` в `.report` PN-05.
Риск остаточный: если в фазе 2 e2e всё же упадёт на каком-то якоре —
локальная поправка = оставить конкретное значение plain (механизм
«plain-список» на ключ — в `tex.js`/конфиг ReportPanel).

### 7.4. Console-чистота (NFR-107)

- `renderToString` (node, 136 рендеров incl. pmatrix/cases/aligned):
  **0 warning / 0 error** при default `strict:'warn'`.
- Chromium-пробы (12 + 10 формул): `console problems: NONE`.
- Остаточные риски:
  1. **404 шрифтов** (проба показывала `net::ERR_FILE_NOT_FOUND` на file://
     без шрифтов) → в приложении Vite бандлит woff2; контроль фазы 2:
     network-лог e2e без 404 + `ls static/assets/*.woff2 == 20`.
  2. Браузерные strict-warning для конкретного sympy-вывода, не пойманного
     в node (разница движков маловероятна, но) → e2e conftest сам падает на
     первом warning (страховка на уровне гейта).
  3. `execCommand("copy")` fallback — в современном chromium не логирует;
     используется только при отказе clipboard API.
- Решение: НЕ выставляем `strict:'ignore'` глобально (маскировало бы проблемы);
  при появлении warning в фазе 2 — точечно: либо править TeX-генерацию, либо
  `onWarning`-колбэк с проглотом (только если warning безобиден).

### 7.5. Прочие

- **Vite 6 + katex.mjs (ESM)**: exports.map `import → katex.mjs` —
  стандартный путь; tree-shaking может не сработать полностью (единый
  модуль) → закладываем 273 КБ в оценку.
- **Производительность**: LSS-13 каталог ~33 Formula, PN-05 ~20, LSS-14 ~12 —
  `renderToString` <1 мс/шт (измерить в фазе 2, бюджет <50 мс на отчёт).
- **`I` в корнях**: `roots` = `{"3 - I": 1}` (str-ключ с `I`),
  `roots_tex` = `{"3 - i": 1}` — фронт использует только `roots_tex`;
  raw-карта для step.text строится по паре `roots`→`roots_tex` по значению
  кратности + порядку (ключи dict сортируются в JSON — детерминизм).

---

## 8. Открытые вопросы

1. **Токены `--pn-formula-*`**: THEME_PLAN.md отсутствует — именовать по
   контракту, координировать с theme-agent до фазы 3 (иначе local-переменные).
2. **`y0p`** (LSS-22): `sp.latex` → `y0p` без штриха. Принять как есть (план)
   или переименовать символ в спеке (риск: ломает `x0`-ассерты? нет — новые
   ключи, но меняется видимый символ; решение — принять как есть).
3. **Каталог LSS-13/18** сейчас рендерится как JSON-ячейки (ReportPanel
   ветка cellText) — включить перестройку в нормальную таблицу (план, п.6)
   или оставить JSON? (Решение плана: перестроить — иначе `law_tex/phi_tex`
   некуда рендерить.)
4. **Права clipboard в e2e**: новый fixture `page_clipboard` с
   `grant_permissions(["clipboard-read","clipboard-write"])` — согласовать
   с owner e2e-контракта (селекторы не трогаем).
5. **Prose-фрагменты вне raw-карты** (`e^{st}`, `s^i`, `t^k` в step.text):
   принять как plain (план) или завести статическую `PROSE_TEX`-карту
   (~10 записей) во tex.js?
6. **Скоп формулы в note/labels** (ANSWER_LABELS `µ′ = µ + W·v(σ)`, notes с
   формулами): по плану plain — подтвердить при ревью (DoD «ноль сырых
   строк» формально касается ВЫВОДОВ решателя; подписи/проза — документация).

## 9. Чек-лист фазы 2 (реализации)

- [ ] `package.json`: `katex@0.19.0` (+ vitest/@vue/test-utils devDeps);
- [ ] `main.js`: импорт `katex.min.css`;
- [ ] `Formula.vue` (§2) + токены в style.css (§3);
- [ ] `frontend/src/math/tex.js` + юнит-тесты (§4.4, §6.2);
- [ ] ReportPanel: ветки 1, 4, 6, 7, 8, 9, 10, 11, 12 (§5.1) + raw→tex замена в step.text;
- [ ] PropertiesPanel: ветки 16–20 (§5.2);
- [ ] backend: `*_tex` (15 distinct-имён ключей, §4.3) + `statement_tex`×23 + `law_tex`×11 + тесты;
- [ ] гейт: `ruff+mypy+pytest` (264 + ~20 зелёные), `npm test` (vitest),
      e2e E2E-1..8 + E2E-10 зелёные, console чистый;
- [ ] скриншоты `docs/acceptance/math/` (§6.3);
- [ ] сверка бандла: 20 woff2 в assets, +~590 КБ (§7.1).
