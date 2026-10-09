#!/usr/bin/env python3
"""Standalone UI / UX / accessibility / performance audit (NOT a pytest test).

Run (containers only, no host installs):

    sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_ui.py"

Writes screenshots to /e2e/screenshots/audit (host: docs/acceptance/audit) and a
JSON digest to /e2e/screenshots/audit/audit_ui.json. Read-only with respect to
product code: it only drives the already-running app and measures timings.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots")) / "audit"
SHOTS.mkdir(parents=True, exist_ok=True)

SMOKE_TEXT = """S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3)."""

# 32-place single-token ring: p_i --t_i--> p_{i+1} (p_33 = p_1), token starts at p1.
def big_ring_json(n: int = 32) -> str:
    places = [f"p{i}" for i in range(1, n + 1)]
    transitions = [f"t{i}" for i in range(1, n + 1)]
    inputs, outputs, im = {}, {}, {}
    for i in range(n):
        src = places[i]
        dst = places[(i + 1) % n]
        inputs[transitions[i]] = {src: 1}
        outputs[transitions[i]] = {dst: 1}
    im = {p: 0 for p in places}
    im[places[0]] = 1
    return json.dumps(
        {
            "places": places,
            "transitions": transitions,
            "inputs": inputs,
            "outputs": outputs,
            "initial_marking": im,
        },
        sort_keys=True,
    )

# Instrumentation: intercept the single window.Registry object (assigned by
# main.js) and every key set on it, plus wrap fetch for per-endpoint timing.
INIT_JS = r"""
(() => {
  const sets = [];
  const netlog = [];
  let _reg = null;
  Object.defineProperty(window, 'Registry', {
    configurable: true,
    get() { return _reg; },
    set(v) {
      const wrapped = new Proxy(v, {
        set(t, k, val) {
          t[k] = val;
          sets.push({ key: String(k), created: !!val, t: Math.round(performance.now()) });
          return true;
        },
      });
      _reg = wrapped;
    },
  });
  const _fetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '?';
    const t0 = performance.now();
    return _fetch(input, init).then((res) => {
      netlog.push({
        url: url,
        status: res.status,
        ms: Math.round(performance.now() - t0),
      });
      return res;
    });
  };
  window.__audit = { sets, netlog };
})();
"""


def shot(name: str, page, full: bool = True) -> str:
    p = SHOTS / name
    page.screenshot(path=str(p), full_page=full)
    return str(p)


def audit_sets(page) -> list:
    return page.evaluate("() => window.__audit ? window.__audit.sets.slice() : []")


def audit_netlog(page) -> list:
    return page.evaluate("() => window.__audit ? window.__audit.netlog.slice() : []")


def cy_node_count(page, key: str) -> int:
    return page.evaluate(
        f"() => (window.Registry && window.Registry.{key})"
        f" ? window.Registry.{key}.$('node').length : -1"
    )


def main() -> None:
    out: dict = {"base_url": BASE_URL, "console": [], "sections": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)

        def on_console(msg):
            if msg.type in ("error", "warning"):
                out["console"].append({"type": msg.type, "text": msg.text})

        def on_pageerror(exc):
            out["console"].append({"type": "pageerror", "text": str(exc)})

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        def wait_analysis(node_count: int, timeout_ms: int = 120000) -> None:
            page.wait_for_function(
                "(count) => {"
                " const s = document.getElementById('graph-stats');"
                " const g = window.Registry && window.Registry.graph;"
                " const active = document.querySelectorAll('#active-list .btn-transition').length;"
                " return !!s && s.textContent.includes('узлов: ' + count)"
                " && !!g && g.$('node').length === count && active >= 1;"
                "}",
                arg=node_count,
                timeout=timeout_ms,
            )

        # ---------------- 1. Full analysis + perf (1503-node graph) ----------
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        shot("01-home-default.png", page)

        t0 = page.evaluate("() => performance.now()")
        page.click("#btn-run-text")
        wait_analysis(1503)
        t1 = page.evaluate("() => performance.now()")
        netlog = audit_netlog(page)
        shot("02-analysis-1503.png", page)
        out["sections"]["perf_full_1503"] = {
            "client_total_ms": round(t1 - t0, 1),
            "net_endpoints": netlog,
            "net_canvas_nodes": cy_node_count(page, "net"),
            "graph_canvas_nodes": cy_node_count(page, "graph"),
            "registry_sets": audit_sets(page),
        }

        # Isolate a re-build of the 1503-node graph: click "Построить граф".
        base_sets = len(audit_sets(page))
        t0 = page.evaluate("() => performance.now()")
        page.click("#btn-build-graph")
        wait_analysis(1503)
        t1 = page.evaluate("() => performance.now()")
        out["sections"]["perf_rebuild_1503"] = {
            "client_total_ms": round(t1 - t0, 1),
            "new_registry_sets": audit_sets(page)[base_sets:],
            "netlog": [n for n in audit_netlog(page) if "/graph" in n["url"] or "/properties" in n["url"]][-3:],
        }

        # ---------------- 2. Cytoscape re-render audit (fire/undo/reset) -----
        sets_before = audit_sets(page)
        def fire_count(key):
            return sum(1 for s in sets_before if s["key"] == key and s["created"])
        # fire one transition via the keyboard-operable button list
        page.locator("#active-list .btn-transition").first.click()
        page.wait_for_timeout(400)
        sets_after_fire = audit_sets(page)
        # undo
        page.click("#btn-undo")
        page.wait_for_timeout(300)
        sets_after_undo = audit_sets(page)
        out["sections"]["rerender_on_fire_undo"] = {
            "net_creates_before": fire_count("net"),
            "sets_delta_fire": sets_after_fire[len(sets_before):],
            "sets_delta_undo": sets_after_undo[len(sets_after_fire):],
            "note": "each 'created:true' set of the same key == a full cytoscape destroy+recreate",
        }

        # ---------------- 3. View switching console (Сеть Петри / Задание) ---
        out["console"] = []
        for _ in range(3):
            page.click("button:has-text('Задание из практикума')")
            page.wait_for_selector(".task-card")
            page.click("button:has-text('Сеть Петри')")
            page.wait_for_selector("#input-text")
        # pick a task, solve, and come back
        page.click("button:has-text('Задание из практикума')")
        page.wait_for_selector(".task-card")
        card = page.locator(".task-card", has_text="TASK-PN-05").first
        card.locator("button", has_text="Решить").click()
        page.wait_for_selector("#task-data")
        page.locator(".solver button.primary", has_text="Решить").click()
        page.wait_for_selector(".report")
        shot("03-home-task-report.png", page)
        page.click("button:has-text('Сеть Петри')")
        page.wait_for_selector("#input-text")
        page.click("button:has-text('Задание из практикума')")
        page.wait_for_selector(".task-card")
        out["sections"]["view_switch_console"] = {
            "errors_warnings": [c for c in out["console"]],
            "count": len(out["console"]),
        }
        shot("04-home-after-switch.png", page)

        # ---------------- 4. Responsiveness 375 / 768 ------------------------
        for width, height, tag in ((375, 667, "mobile375"), (768, 1024, "tablet768")):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(250)
            page.click("button:has-text('Сеть Петри')")
            page.wait_for_selector("#input-text")
            page.wait_for_timeout(250)
            overflow = page.evaluate(
                "() => ({ scroll: document.documentElement.scrollWidth,"
                " client: document.documentElement.clientWidth,"
                " overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth })"
            )
            canvas_box = page.evaluate(
                "() => { const el = document.getElementById('canvas-net');"
                " const r = el ? el.getBoundingClientRect() : null;"
                " return r ? {w: Math.round(r.width), h: Math.round(r.height)} : null; }"
            )
            shot(f"05-{tag}-net.png", page)
            out["sections"][f"responsive_{tag}"] = {
                "viewport": {"w": width, "h": height},
                "overflow": overflow,
                "net_canvas_box": canvas_box,
            }
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(200)

        # ---------------- 5. Window resize behaviour -------------------------
        page.click("button:has-text('Сеть Петри')")
        page.wait_for_selector("#input-text")
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(300)
        ext_before = page.evaluate(
            "() => { const g = window.Registry && window.Registry.graph;"
            " return g ? g.extent() : null; }"
        )
        page.set_viewport_size({"width": 700, "height": 600})
        page.wait_for_timeout(500)
        ext_after = page.evaluate(
            "() => { const g = window.Registry && window.Registry.graph;"
            " const c = document.getElementById('canvas-graph');"
            " const r = c ? c.getBoundingClientRect() : null;"
            " return g ? { extent: g.extent(), canvas_w: r ? Math.round(r.width) : null } : null; }"
        )
        out["sections"]["window_resize"] = {
            "extent_before": ext_before,
            "after_700x600": ext_after,
            "note": "extent unchanged => graph not re-fit after container resize",
        }
        shot("06-resize-700.png", page)
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(200)

        # ---------------- 6. Keyboard accessibility --------------------------
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.click("#btn-run-text")
        wait_analysis(1503)
        page.evaluate("() => document.body.focus()")
        focus_seq = []
        seen = set()
        for _ in range(40):
            page.keyboard.press("Tab")
            info = page.evaluate(
                "() => { const el = document.activeElement;"
                " if (!el || el === document.body) return {sel: '(body)'};"
                " const cs = getComputedStyle(el);"
                " const hasRing = (cs.outlineWidth !== '0px' && cs.outlineStyle !== 'none')"
                " || cs.boxShadow !== 'none';"
                " let sel = el.tagName.toLowerCase();"
                " if (el.id) sel += '#' + el.id;"
                " else if (el.className && typeof el.className === 'string') sel += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');"
                " return {sel, hasFocusRing: hasRing, text: (el.textContent||'').trim().slice(0,24)}; }"
            )
            key = info.get("sel")
            if key in seen:
                break
            seen.add(key)
            focus_seq.append(info)
        out["sections"]["keyboard_tab_order"] = {
            "sequence": focus_seq,
            "reached_canvas": any("canvas" in f.get("sel", "") for f in focus_seq),
            "reached_history_line": any("history-line" in f.get("sel", "") for f in focus_seq),
        }
        # focus a transition button and try Enter (keyboard firing)
        page.evaluate("() => { const b = document.querySelector('#active-list .btn-transition'); if (b) b.focus(); }")
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        out["sections"]["keyboard_fire_enter"] = {
            "history_lines": page.evaluate(
                "() => document.querySelectorAll('#history-list .history-line').length"
            ),
        }
        shot("07-keyboard-focus.png", page)

        # ---------------- 7. 32-place net build+properties -------------------
        page.goto(BASE_URL)
        page.wait_for_selector("#tab-json")
        page.click("#tab-json")
        page.fill("#input-json", big_ring_json(32))
        page.click("#btn-run-json")
        wait_analysis(32, timeout_ms=120000)
        netlog = audit_netlog(page)
        shot("08-big32-analysis.png", page)
        out["sections"]["perf_big32"] = {
            "net_endpoints": netlog,
            "net_canvas_nodes": cy_node_count(page, "net"),
            "graph_canvas_nodes": cy_node_count(page, "graph"),
        }

        browser.close()

    # Persist + print
    digest_path = SHOTS / "audit_ui.json"
    digest_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n[audit_ui] digest -> {digest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
