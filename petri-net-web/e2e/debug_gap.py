# Diagnostic UI gap scenarios (compatibility part 2). Standalone script, NOT pytest.
# Run inside the e2e container:  cd /e2e && python debug_gap.py
# Screenshots + results.json -> /e2e/screenshots/gap/ (host: docs/acceptance/gap/).

import json
import os
import struct
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
GAP_DIR = Path(os.environ.get("GAP_DIR", "/e2e/screenshots/gap"))
GAP_DIR.mkdir(parents=True, exist_ok=True)

SMOKE_TEXT = """S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3)."""

SMOKE_NET = {
    "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
    "transitions": ["t1", "t2", "t3", "t4", "t5"],
    "inputs": {
        "t1": {"p1": 2},
        "t2": {"p1": 1, "p6": 1},
        "t3": {"p2": 1},
        "t4": {"p2": 1, "p3": 1, "p4": 2},
        "t5": {"p5": 2},
    },
    "outputs": {
        "t1": {"p2": 1},
        "t2": {"p3": 2},
        "t3": {"p4": 3},
        "t4": {"p5": 1, "p6": 1},
        "t5": {"p1": 1, "p3": 1},
    },
    "initial_marking": {"p1": 7, "p2": 4, "p3": 2, "p4": 5, "p5": 4, "p6": 3},
}
SMOKE_JSON = json.dumps(SMOKE_NET, sort_keys=True)

# (direction, source, target, weight) for all 15 arcs of the smoke net
FORM_ARCS = [
    ("input", "p1", "t1", 2),
    ("output", "t1", "p2", 1),
    ("input", "p1", "t2", 1),
    ("input", "p6", "t2", 1),
    ("output", "t2", "p3", 2),
    ("input", "p2", "t3", 1),
    ("output", "t3", "p4", 3),
    ("input", "p2", "t4", 1),
    ("input", "p3", "t4", 1),
    ("input", "p4", "t4", 2),
    ("output", "t4", "p5", 1),
    ("output", "t4", "p6", 1),
    ("input", "p5", "t5", 2),
    ("output", "t5", "p1", 1),
    ("output", "t5", "p3", 1),
]

INIT_LABELS = ["p1 (7)", "p2 (4)", "p3 (2)", "p4 (5)", "p5 (4)", "p6 (3)"]

RESULTS = {"scenarios": {}}


class Scenario:
    def __init__(self, key, title):
        self.key = key
        self.title = title
        self.steps = []
        self.console_errors = []
        self.console_warnings = []
        self.page_errors = []
        self.screenshot = None
        self.error = None

    def step(self, name, expected, fact, ok=None):
        self.steps.append({"step": name, "expected": expected, "fact": fact, "ok": ok})
        mark = "" if ok is None else (" OK" if ok else " FAIL")
        print(f"  [{self.key}] {name}: {fact}{mark}", flush=True)

    def finish(self, page, shot_name):
        try:
            path = GAP_DIR / f"{shot_name}.png"
            page.screenshot(path=str(path), full_page=True)
            self.screenshot = f"docs/acceptance/gap/{shot_name}.png"
        except Exception as err:  # noqa: BLE001
            print(f"  [{self.key}] screenshot failed: {err}", flush=True)


def attach_console(page, sc: Scenario):
    def on_console(msg):
        if msg.type == "error":
            sc.console_errors.append(msg.text)
        elif msg.type == "warning":
            sc.console_warnings.append(msg.text)

    def on_pageerror(err):
        sc.page_errors.append(str(err))

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)


def wait_analysis(page: Page, count: int = 1503, timeout_ms: int = 120000) -> None:
    page.wait_for_function(
        "(count) => {"
        " const s = document.getElementById('graph-stats');"
        " const g = window.Registry && window.Registry.graph;"
        " const active = document.querySelectorAll('#active-list .btn-transition').length;"
        " return !!s && s.textContent.includes('узлов: ' + count)"
        " && !!g && g.$('node').length === count && active >= 1;"
        "}",
        arg=count,
        timeout=timeout_ms,
    )


def wait_net_label(page: Page, label: str, timeout_ms: int = 15000) -> None:
    page.wait_for_function(
        "(label) => {"
        " const g = window.Registry && window.Registry.net;"
        " return !!g && g.$('node').some((n) => n.data('label') === label);"
        "}",
        arg=label,
        timeout=timeout_ms,
    )


def net_state(page: Page):
    return page.evaluate(
        "() => {"
        " const g = window.Registry && window.Registry.net;"
        " if (!g) return {labels: [], edges: 0, shapes: {}};"
        " const shapes = {};"
        " g.$('node').forEach((n) => { shapes[n.data('label')] = n.style('shape'); });"
        " return { labels: g.$('node').map((n) => n.data('label')), edges: g.$('edge').length,"
        "  shapes: shapes,"
        "  edgeWeights: g.$('edge').map((e) => e.data('weight')).filter((w) => w > 1) };"
        "}"
    )


def props_data(page: Page):
    return page.evaluate(
        "() => Array.from(document.querySelectorAll('#props dt')).map((d) => d.textContent)"
    )


def toast_text(page: Page, timeout_ms: int = 8000) -> str:
    try:
        page.wait_for_selector("#toast:not(.hidden)", timeout=timeout_ms)
        return page.inner_text("#toast")
    except PWTimeout:
        return ""


def run_text(page: Page) -> None:
    page.goto(BASE_URL)
    page.wait_for_selector("#input-text")
    page.fill("#input-text", SMOKE_TEXT)
    page.click("#btn-run-text")
    wait_analysis(page)


def png_info(path: Path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return {"valid": False, "size": len(data)}
    width, height = struct.unpack(">II", data[16:24])
    return {"valid": True, "size": len(data), "width": width, "height": height}


def try_png_export(page: Page):
    """Click the PNG export button; return a dict describing the outcome."""
    got = []
    page.on("download", lambda d: got.append(d))
    page.click("#btn-export-png")
    toast = ""
    try:
        page.wait_for_selector("#toast:not(.hidden)", timeout=7000)
        toast = page.inner_text("#toast")
        page.screenshot(path=str(GAP_DIR / "g-png-fail.png"), full_page=False)
    except PWTimeout:
        pass
    t0 = time.monotonic()
    while not got and time.monotonic() - t0 < 5:
        page.wait_for_timeout(300)
    if got:
        d = got[0]
        name = d.suggested_filename()
        target = GAP_DIR / f"export-{name}"
        d.save_as(str(target))
        return {"downloaded": True, "name": name, **png_info(target)}
    if not toast:
        page.screenshot(path=str(GAP_DIR / "g-png-fail.png"), full_page=False)
    return {"downloaded": False, "toast": toast or "(пусто)"}


def is_valid_png(res: dict) -> bool:
    return bool(res) and res.get("downloaded") and res.get("valid")


def scenario_a(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    page.goto(BASE_URL)
    page.wait_for_selector("#input-text")

    prefill = page.input_value("#input-text")
    sc.step(
        "prefill",
        "текстовая вкладка предзаполнена эталонной сетью",
        f"value не пусто={bool(prefill.strip())}, содержит µ=(7,4,2,5,4,3)="
        f"{'µ = (7, 4, 2, 5, 4, 3)' in prefill}, равно SMOKE={'Y' if prefill == SMOKE_TEXT else 'N'}",
        ok=bool(prefill.strip()) and "µ = (7, 4, 2, 5, 4, 3)" in prefill,
    )
    btn_label = page.inner_text("#btn-run-text")
    sc.step("button-label", "кнопка «Построить/Проанализировать»", f"факт: «{btn_label}»")

    t0 = time.monotonic()
    page.click("#btn-run-text")
    wait_analysis(page)
    elapsed = time.monotonic() - t0
    sc.step("analyze", "граф построен (1503 узлов)", f"время: {elapsed:.1f} c", ok=True)

    st = net_state(page)
    places_ok = all(l in st["labels"] for l in INIT_LABELS)
    sc.step(
        "net-places",
        "кружки p1..p6 с числом фишек: " + ", ".join(INIT_LABELS),
        f"labels={st['labels']}, shapes={st['shapes']}",
        ok=places_ok,
    )
    trans_ok = all(t in st["labels"] for t in ["t1", "t2", "t3", "t4", "t5"])
    trans_shapes = {st["shapes"].get(t) for t in ["t1", "t2", "t3", "t4", "t5"]}
    sc.step(
        "net-transitions",
        "прямоугольники t1..t5",
        f"присутствуют={trans_ok}, shapes={trans_shapes}, edges={st['edges']}, weights>1={st['edgeWeights']}",
        ok=trans_ok and st["edges"] == 15,
    )
    edge_labels = page.evaluate(
        "() => { const g = window.Registry.net; const edges = g.$('edge');"
        " const labelOf = (e) => e.pstyle('label').value;"
        " return { total: edges.length,"
        "  weight1_showing_1: edges.filter((e) => e.data('weight') === 1 && labelOf(e) === '1').length,"
        "  weight_gt1_hidden: edges.filter((e) => e.data('weight') > 1 && labelOf(e) === '').length,"
        "  distinct_labels: Array.from(new Set(edges.map(labelOf))) } }"
    )
    sc.step(
        "weight-labels",
        "подписи весов: дуги с весом > 1 показывают вес (FR-015.1), дуги с весом 1 — без подписи (намерение стиля)",
        f"вес>1 без подписи: {edge_labels['weight_gt1_hidden']}/{edge_labels['total']},"
        f" вес=1 с подписью «1»: {edge_labels['weight1_showing_1']}, разные label: {edge_labels['distinct_labels']}"
        " (невалидный селектор edge[data(weight) = 1] чистит label у ВСЕХ дуг)",
        ok=edge_labels["weight_gt1_hidden"] == 0 and edge_labels["weight1_showing_1"] == 0,
    )
    page.screenshot(path=str(GAP_DIR / "a-net-initial.png"), full_page=False)

    active = page.evaluate(
        "() => Array.from(document.querySelectorAll('#active-list .btn-transition'))"
        ".map((b) => b.textContent + ':' + b.className)"
    )
    sc.step(
        "active-list",
        "активные переходы подсвечены (5 кнопок t1..t5)",
        f"активен список: {active}",
        ok=len(active) == 5,
    )
    net_highlight = page.evaluate(
        "() => {"
        " const g = window.Registry.net; const out = {};"
        " ['t1','t2','t3','t4','t5'].forEach((t) => {"
        "   const n = g.getElementById('t:' + t);"
        "   out[t] = { classes: Array.from(n.classes()), selected: n.selected() };"
        " }); return out;"
        "}"
    )
    sc.step(
        "net-canvas-highlight",
        "на канвасе сети активные переходы визуально выделены",
        f"classes/selected на канвасе: {net_highlight} (нет отдельного стиля активных)",
        ok=False if all(v["classes"] == [] and not v["selected"] for v in net_highlight.values()) else None,
    )

    # click transition t1: per FR-017.2 selecting must fire it
    page.click("#active-list .btn-transition[data-transition='t1']")
    page.wait_for_timeout(700)
    after_click = net_state(page)["labels"]
    fired_on_click = "p1 (5)" in after_click
    sc.step(
        "click-t1-fires",
        "клик по переходу t1 -> сразу срабатывание (FR-017.2), маркировка p1 (5)",
        f"после клика labels={after_click} (fired={fired_on_click}); нужен ли доп. клик «Шаг»?",
        ok=fired_on_click,
    )
    page.click("#btn-step")
    wait_net_label(page, "p1 (5)")
    st2 = net_state(page)["labels"]
    sc.step(
        "step-t1",
        "после «Шаг» маркировка (5,5,2,5,4,3)",
        f"labels={st2}",
        ok="p1 (5)" in st2 and "p2 (5)" in st2,
    )
    anim = page.evaluate(
        "() => { const el = document.getElementById('canvas-net'); "
        " return getComputedStyle(el).transition; }"
    )
    sc.step("animation", "анимация срабатывания", f"CSS transition канваса: «{anim}» (Cytoscape canvas, без анимации)", ok=None)
    page.screenshot(path=str(GAP_DIR / "a-after-step.png"), full_page=True)
    sc.finish(page, "a-text-intake")
    page.close()


def scenario_b(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    page.goto(BASE_URL)
    page.wait_for_selector("#tab-json")
    page.click("#tab-json")
    page.fill("#input-json", SMOKE_JSON)
    page.click("#btn-run-json")
    wait_analysis(page)
    st = net_state(page)
    places_ok = all(l in st["labels"] for l in INIT_LABELS)
    graph_count = page.evaluate("() => window.Registry.graph.$('node').length")
    sc.step(
        "json-intake",
        "JSON -> тот же результат, что и текстовый ввод (1503 узлов, те же маркировки)",
        f"graph_nodes={graph_count}, net_labels={st['labels']}",
        ok=graph_count == 1503 and places_ok and st["edges"] == 15,
    )
    props = page.inner_text("#props")
    sc.step("props-equal", "свойства совпадают со сценарием (a)", f"29={'29' in props}, L1={'L1' in props}, 23={'23' in props}")
    page.screenshot(path=str(GAP_DIR / "b-json-intake.png"), full_page=True)
    sc.finish(page, "b-json-intake")
    page.close()


def scenario_c(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    page.goto(BASE_URL)
    page.wait_for_selector("#tab-form")
    page.click("#tab-form")
    page.fill("#form-places", "p1, p2, p3, p4, p5, p6")
    page.fill("#form-transitions", "t1, t2, t3, t4, t5")
    page.fill("#form-marking", "7, 4, 2, 5, 4, 3")
    rows = page.locator("#arcs-list .arc-row")
    for i in range(1, len(FORM_ARCS)):
        page.click("#btn-add-arc")
    rows = page.locator("#arcs-list .arc-row")
    assert rows.count() == len(FORM_ARCS), f"arc rows {rows.count()}"
    for i, (direction, src, tgt, weight) in enumerate(FORM_ARCS):
        row = rows.nth(i)
        row.locator(".arc-direction").select_option(direction)
        row.locator(".arc-source").fill(src)
        row.locator(".arc-target").fill(tgt)
        row.locator(".arc-weight").fill(str(weight))
    page.screenshot(path=str(GAP_DIR / "c-form-filled.png"), full_page=True)
    page.click("#btn-run-form")
    wait_analysis(page)
    st = net_state(page)
    graph_count = page.evaluate("() => window.Registry.graph.$('node').length")
    places_ok = all(l in st["labels"] for l in INIT_LABELS)
    sc.step(
        "form-intake",
        "форма (15 дуг + маркировка) -> та же сеть: 1503 узлов, 15 дуг, начальные labels",
        f"graph_nodes={graph_count}, edges={st['edges']}, labels={st['labels']}",
        ok=graph_count == 1503 and places_ok and st["edges"] == 15,
    )
    sc.finish(page, "c-form-intake")
    page.close()


def scenario_d(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    run_text(page)

    page.click("#active-list .btn-transition[data-transition='t2']")
    page.click("#btn-step")
    wait_net_label(page, "p1 (6)")
    labels1 = net_state(page)["labels"]
    sc.step("step-t2", "t2: (7,4,2,5,4,3)->(6,4,4,5,4,2)", f"labels={labels1}", ok="p1 (6)" in labels1 and "p3 (4)" in labels1 and "p6 (2)" in labels1)

    page.click("#active-list .btn-transition[data-transition='t3']")
    page.click("#btn-step")
    wait_net_label(page, "p4 (8)")
    labels2 = net_state(page)["labels"]
    sc.step("step-t3", "t3: ->(6,3,4,8,4,2)", f"labels={labels2}", ok="p4 (8)" in labels2)

    page.click("#btn-undo")
    wait_net_label(page, "p4 (5)")
    sc.step("undo", "undo возвращает (6,4,4,5,4,2)", f"labels={net_state(page)['labels']}", ok="p4 (5)" in net_state(page)["labels"])

    page.click("#btn-reset")
    page.wait_for_function(
        "() => document.querySelectorAll('#history-list .history-line').length === 0", timeout=15000
    )
    labels_r = net_state(page)["labels"]
    sc.step("reset", "reset -> µ0 и пустая история", f"labels={labels_r}", ok=all(l in labels_r for l in INIT_LABELS))

    # history click -> return to that step
    page.click("#active-list .btn-transition[data-transition='t1']")
    page.click("#btn-step")
    wait_net_label(page, "p1 (5)")
    page.click("#active-list .btn-transition[data-transition='t2']")
    page.click("#btn-step")
    wait_net_label(page, "p1 (4)")
    hist = page.evaluate(
        "() => Array.from(document.querySelectorAll('#history-list .history-line'))"
        ".map((h) => h.textContent)"
    )
    sc.step("history-list", "история: 2 строки шагов", f"{hist}")
    clickable = page.evaluate(
        "() => {"
        " const el = document.querySelector('#history-list .history-line');"
        " if (!el) return {found: false};"
        " const cs = getComputedStyle(el);"
        " return {found: true, cursor: cs.cursor, tag: el.tagName, class: el.className};"
        "}"
    )
    if clickable.get("found"):
        page.locator("#history-list .history-line").first.click()
        page.wait_for_timeout(700)
        after = net_state(page)["labels"]
        reverted = "p1 (7)" in after
        sc.step(
            "history-click",
            "клик по шагу в истории -> возврат к этой маркировке (сценарий пользователя)",
            f"cursor={clickable['cursor']}, после клика labels={after} (вернулось к µ0={reverted})",
            ok=reverted,
        )
    else:
        sc.step("history-click", "клик по шагу в истории -> возврат", "строки истории не найдены", ok=False)
    page.screenshot(path=str(GAP_DIR / "d-history.png"), full_page=True)
    sc.finish(page, "d-stepping")
    page.close()


def scenario_e(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    run_text(page)

    count = page.evaluate("() => window.Registry.graph.$('node').length")
    t0 = time.monotonic()
    page.evaluate("() => 1 + 1")
    responsive_ms = (time.monotonic() - t0) * 1000
    sc.step(
        "graph-render",
        "1503 узла рендерятся, страница не вешается",
        f"nodes={count}, time-to-evaluate={responsive_ms:.0f} ms",
        ok=count == 1503 and responsive_ms < 1000,
    )

    node = page.evaluate(
        "() => {"
        " const g = window.Registry.graph;"
        " const n = g.$('node').find((x) => x.data('label') === '5,5,2,5,4,3');"
        " if (!n) return null; const pos = n.renderedPosition();"
        " return {id: n.id(), x: pos.x, y: pos.y, classes: Array.from(n.classes())};"
        "}"
    )
    if node is None:
        sc.step("find-node", "узел с маркировкой 5,5,2,5,4,3", "не найден", ok=False)
    else:
        box = page.locator("#canvas-graph").bounding_box()
        t0 = time.monotonic()
        page.mouse.click(box["x"] + node["x"], box["y"] + node["y"])
        try:
            wait_net_label(page, "p1 (5)", timeout_ms=5000)
            switch_ms = (time.monotonic() - t0) * 1000
            switched = True
        except PWTimeout:
            switch_ms = (time.monotonic() - t0) * 1000
            switched = False
        labels = net_state(page)["labels"]
        sc.step(
            "goto-node",
            "клик по узлу -> смена маркировки сети ≤ 2 c (FR-016.4)",
            f"node={node['id']}, switch_ms={switch_ms:.0f}, switched={switched}, labels={labels}",
            ok=switched,
        )
        bg_before = page.evaluate(
            "() => { const g = window.Registry.graph; const n = g.getElementById('n2');"
            " return n ? n.pstyle('background-color').value : null; }"
        )
        highlighted = page.evaluate(
            "(id) => {"
            " const n = window.Registry.graph.getElementById(id);"
            " return {classes: Array.from(n.classes()), selected: n.selected(),"
            "  bg: n.pstyle('background-color').value};"
            "}",
            node["id"],
        )
        is_current = bool(highlighted["classes"]) or highlighted["selected"]
        visual = highlighted["bg"] != bg_before
        sc.step(
            "current-highlight",
            "кликнутый узел подсвечен как текущий (FR-016.2): state selected + видимый стиль",
            f"classes={highlighted['classes']}, selected={highlighted['selected']},"
            f" bg_clicked={highlighted['bg']}, bg_other_node={bg_before}, визуально отличается={visual}"
            " (в стилисте graph-canvas.js нет правила :selected/current)",
            ok=visual,
        )
        # does the selection follow state changes (step)?
        page.click("#active-list .btn-transition[data-transition='t2']")
        page.click("#btn-step")
        wait_net_label(page, "p1 (4)", timeout_ms=10000)
        sel_state = page.evaluate(
            "() => { const g = window.Registry.graph;"
            " const sel = Array.from(g.nodes(':selected')).map((n) => n.id());"
            " const cur = g.$('node').find((x) => x.data('label') === '4,5,4,5,4,2');"
            " return {selected: sel, current_node: cur ? cur.id() : null}; }"
        )
        sc.step(
            "selection-sync",
            "выделение на канвасе следует за текущей маркировкой (после step)",
            f"selected после step={sel_state['selected']}, узел текущей маркировки={sel_state['current_node']},"
            f" кликнуто было {node['id']}",
            ok=sel_state["selected"] == [sel_state["current_node"]],
        )
        page.screenshot(path=str(GAP_DIR / "e-graph-goto.png"), full_page=True)
    sc.finish(page, "e-reachability-graph")
    page.close()


def scenario_f(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    run_text(page)
    labels = props_data(page)
    sc.step("props-labels", "панель свойств: таблица свойство->значение", f"наименования: {labels}")
    text = page.inner_text("#props")
    glossary = {
        "живая сеть (классификация)": "жив" in text.lower(),
        "тупиковая сеть (классификация)": "тупиковая" in text.lower(),
        "частичнотупиковая": "частичнотупиков" in text.lower(),
        "k-ограниченная": "k-ограниченн" in text.lower() or "к-ограниченн" in text.lower(),
        "безопасная": "безопасн" in text.lower(),
        "консервативная": "консервативн" in text.lower(),
    }
    sc.step(
        "glossary-match",
        "названия свойств совпадают с глоссарием методички §5.1 (живая/тупиковая/частичнотупиковая, k-ограниченная, безопасная, консервативная)",
        f"найдено в тексте: {glossary}",
        ok=all(glossary.values()),
    )
    sc.step(
        "actual-terms",
        "фактические термины UI",
        "Ограничена (bounded); Глобальная k; Безопасна (safe); Ограниченность по позициям; Живость (уровень сети) L0-L4; Живость по переходам; Тупики (deadlocks); Мёртвые переходы; Обратимость (home state); Без тупиков (deadlock-free)",
        ok=None,
    )
    page.screenshot(path=str(GAP_DIR / "f-properties.png"), full_page=True)
    sc.finish(page, "f-properties-panel")
    page.close()


def scenario_g(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    run_text(page)

    png_type = page.evaluate(
        "() => { const r = window.Registry.net.png({scale:1, bg:'#fff'});"
        " return {type: typeof r, head: String(r).slice(0, 30)}; }"
    )
    sc.step(
        "png-api-probe",
        "cy.png() возвращает Promise (нужно для .then в exports.js)",
        f"typeof={png_type['type']}, head={png_type['head']!r} (default output в cytoscape 3.30.2 = строка data-URI, опция outputType неизвестна)",
        ok=png_type["type"] == "object",
    )

    page.click("#canvas-net")
    net_dl = try_png_export(page)
    sc.step(
        "export-png-net",
        "PNG графа сети скачивается и валиден",
        f"download={net_dl}",
        ok=is_valid_png(net_dl),
    )

    page.click("#canvas-graph")
    graph_dl = try_png_export(page)
    sc.step(
        "export-png-graph",
        "PNG графа достижимости скачивается и валиден",
        f"download={graph_dl}",
        ok=is_valid_png(graph_dl),
    )

    with page.expect_download(timeout=60000) as dl:
        page.click("#btn-export-json")
    rpt_path = GAP_DIR / "export-report.json"
    dl.value.save_as(str(rpt_path))
    try:
        report = json.loads(rpt_path.read_text(encoding="utf-8"))
        has_cons = any("conserv" in k.lower() for k in report)
        sc.step(
            "export-json",
            "JSON отчёт валиден (1503/4983, k=29, L1, 23 тупика)",
            f"global_k={report.get('global_k')}, liveness={report.get('liveness', {}).get('level')}, "
            f"deadlocks={len(report.get('deadlocks', []))}, keys={sorted(report.keys())}, консервативность в отчёте={has_cons}",
            ok=report.get("global_k") == 29 and len(report.get("deadlocks", [])) == 23,
        )
    except Exception as err:  # noqa: BLE001
        sc.step("export-json", "JSON отчёт валиден", f"parse error: {err}", ok=False)

    with page.expect_download(timeout=60000) as dl:
        page.click("#btn-export-csv")
    csv_path = GAP_DIR / "export-markings.csv"
    dl.value.save_as(str(csv_path))
    lines = csv_path.read_text(encoding="utf-8").strip().split("\n")
    sc.step(
        "export-csv",
        "CSV маркировок: заголовок + 1503 строки",
        f"header={lines[0]}, rows={len(lines) - 1}, first={lines[1] if len(lines) > 1 else None}",
        ok=len(lines) == 1504 and lines[0] == "p1,p2,p3,p4,p5,p6",
    )
    sc.finish(page, "g-exports")
    page.close()


def scenario_h(browser, sc: Scenario):
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc)
    run_text(page)
    page.click("#btn-sessions")
    page.wait_for_selector("#sessions-panel:not(.hidden)")
    before = page.locator("#sessions-list .session-item").count()
    sc.step("sessions-list", "список сессий не пуст", f"сессий: {before} (в списке нет лимита; «сохранить» явно нет — сессия создаётся автоматически при анализе)")
    save_btns = page.evaluate(
        "() => Array.from(document.querySelectorAll('button'))"
        ".map((b) => b.id + ':' + b.textContent.trim()).filter((s) => /сохран|save/i.test(s))"
    )
    sc.step("save-button", "явная кнопка «Сохранить»", f"кнопок с «сохран/save»: {save_btns or 'нет'} (FR-022.1: автосохранение при анализе)", ok=None)

    current = page.evaluate(
        "() => Array.from(document.querySelectorAll('#sessions-list .session-item'))"
        ".map((b) => b.textContent + (b.classList.contains('current') ? ' [current]' : ''))"
    )
    sc.step("current-marked", "текущая сессия помечена", f"{current[:8]}{'...' if len(current) > 8 else ''}")

    page.locator("#sessions-list .session-item").first.click()
    wait_analysis(page, timeout_ms=60000)
    count = page.evaluate("() => window.Registry.graph.$('node').length")
    sc.step("restore", "клик по сессии -> восстановление (1503 узлов)", f"graph_nodes={count}", ok=count == 1503)
    page.screenshot(path=str(GAP_DIR / "h-sessions.png"), full_page=True)

    remove_btns = page.locator("#sessions-list .session-remove")
    n_remove = remove_btns.count()
    remove_btns.first.click()
    page.wait_for_timeout(1500)
    after = page.locator("#sessions-list .session-item").count()
    cleared = page.evaluate("() => document.getElementById('analysis').classList.contains('hidden')")
    sc.step(
        "delete",
        "удаление сессии: исчезла из списка; текущая -> вид очищен",
        f"кнопок удаления: {n_remove}, до: {before}, после: {after}, analysis-cleared={cleared}",
        ok=after < before,
    )
    sc.finish(page, "h-sessions")
    page.close()


def scenario_i(browser):
    # i1: broken JSON
    sc1 = Scenario("i1", "broken JSON")
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc1)
    page.goto(BASE_URL)
    page.click("#tab-json")
    page.fill("#input-json", "{ this is not json ]")
    page.click("#btn-run-json")
    t = toast_text(page)
    analysis_shown = page.evaluate("() => !document.getElementById('analysis').classList.contains('hidden')")
    sc1.step("broken-json", "читаемая ошибка, без console-ошибок", f"toast=«{t}», analysis_shown={analysis_shown}", ok=bool(t) and not analysis_shown)
    sc1.finish(page, "i1-broken-json")
    page.close()
    RESULTS["scenarios"]["i1"] = sc1

    # i2: malformed text
    sc2 = Scenario("i2", "malformed text")
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc2)
    page.goto(BASE_URL)
    page.fill("#input-text", "Привет, мир. Это не сеть Петри.")
    page.click("#btn-run-text")
    t = toast_text(page)
    analysis_shown = page.evaluate("() => !document.getElementById('analysis').classList.contains('hidden')")
    sc2.step("bad-text", "читаемая ошибка (RU), без console-ошибок", f"toast=«{t}», analysis_shown={analysis_shown}", ok=bool(t) and not analysis_shown)
    sc2.finish(page, "i2-bad-text")
    page.close()
    RESULTS["scenarios"]["i2"] = sc2

    # i3: empty text net
    sc3 = Scenario("i3", "empty net")
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc3)
    page.goto(BASE_URL)
    page.fill("#input-text", "")
    page.click("#btn-run-text")
    t = toast_text(page)
    status = page.inner_text("#status-line")
    analysis_shown = page.evaluate("() => !document.getElementById('analysis').classList.contains('hidden')")
    sc3.step("empty-text", "пустая сеть -> читаемая ошибка", f"toast=«{t}», status=«{status}», analysis_shown={analysis_shown}")
    # form: no places
    page.click("#tab-form")
    page.fill("#form-places", "")
    page.click("#btn-run-form")
    t2 = toast_text(page)
    sc3.step("empty-form", "форма без позиций -> читаемая ошибка", f"toast=«{t2}»", ok=bool(t2))
    sc3.finish(page, "i3-empty-net")
    page.close()
    RESULTS["scenarios"]["i3"] = sc3

    # i4: negative arc weight in form
    sc4 = Scenario("i4", "negative weight form")
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc4)
    page.goto(BASE_URL)
    page.click("#tab-form")
    page.fill("#form-places", "p1, p2")
    page.fill("#form-transitions", "t1")
    page.fill("#form-marking", "1, 0")
    row = page.locator("#arcs-list .arc-row").first
    row.locator(".arc-direction").select_option("input")
    row.locator(".arc-source").fill("p1")
    row.locator(".arc-target").fill("t1")
    row.locator(".arc-weight").fill("-1")
    page.click("#btn-run-form")
    page.wait_for_timeout(2500)
    t = toast_text(page, timeout_ms=1000)
    graph_nodes = page.evaluate(
        "() => (window.Registry && window.Registry.graph) ? window.Registry.graph.$('node').length : 0"
    )
    edges = net_state(page)["edges"]
    weight = page.evaluate(
        "() => (window.Registry && window.Registry.net) ? window.Registry.net.$('edge').first().data('weight') : null"
    )
    sc4.step(
        "negative-weight",
        "отрицательный вес дуги -> читаемая ошибка валидации",
        f"toast=«{t}», сеть построена (graph_nodes={graph_nodes}, edges={edges}, weight_дуги={weight}) — вес тихо заменили на 1",
        ok=bool(t) and graph_nodes == 0,
    )
    sc4.finish(page, "i4-negative-weight")
    page.close()
    RESULTS["scenarios"]["i4"] = sc4

    # i5: negative weight in JSON
    sc5 = Scenario("i5", "negative weight json")
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    attach_console(page, sc5)
    page.goto(BASE_URL)
    page.click("#tab-json")
    bad = dict(SMOKE_NET)
    bad["inputs"] = {"t1": {"p1": -2}}
    bad["outputs"] = {"t1": {"p2": 1}}
    page.fill("#input-json", json.dumps(bad))
    page.click("#btn-run-json")
    t = toast_text(page)
    analysis_shown = page.evaluate("() => !document.getElementById('analysis').classList.contains('hidden')")
    sc5.step("negative-weight-json", "отрицательный вес в JSON -> читаемая ошибка", f"toast=«{t}», analysis_shown={analysis_shown}", ok=bool(t) and not analysis_shown)
    sc5.finish(page, "i5-negative-json")
    page.close()
    RESULTS["scenarios"]["i5"] = sc5


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for key, title, fn in [
            ("a", "text intake + net + stepping click", scenario_a),
            ("b", "JSON intake comparison", scenario_b),
            ("c", "form intake", scenario_c),
            ("d", "stepping + history click", scenario_d),
            ("e", "reachability graph click-to-goto", scenario_e),
            ("f", "properties panel terminology", scenario_f),
            ("g", "exports", scenario_g),
            ("h", "sessions", scenario_h),
        ]:
            sc = Scenario(key, title)
            try:
                fn(browser, sc)
            except Exception as err:  # noqa: BLE001
                sc.error = f"{type(err).__name__}: {err}"
                print(f"  [{key}] SCENARIO ERROR: {sc.error}", flush=True)
            RESULTS["scenarios"][key] = sc
        scenario_i(browser)

    out = {}
    for key, sc in RESULTS["scenarios"].items():
        out[key] = {
            "title": sc.title,
            "steps": sc.steps,
            "console_errors": sc.console_errors,
            "console_warnings": sc.console_warnings,
            "page_errors": sc.page_errors,
            "screenshot": sc.screenshot,
            "error": sc.error,
        }
        print(
            f"\n== {key} ({sc.title}): console_errors={len(sc.console_errors)} "
            f"warnings={len(sc.console_warnings)} page_errors={len(sc.page_errors)} "
            f"error={sc.error} shot={sc.screenshot}",
            flush=True,
        )
    (GAP_DIR / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nresults -> {GAP_DIR / 'results.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
