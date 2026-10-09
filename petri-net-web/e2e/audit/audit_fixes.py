#!/usr/bin/env python3
"""Standalone audit of the P0/P1/P2 fixes (iteration 3, round: ui-agent).

NOT a pytest test; read-only w.r.t. product code (drives the running app).

Run:
    sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_fixes.py"

Checks (each maps to an AC from docs/AUDIT_REPORT.md):
  1. double-render  (P1#4): exactly ONE window.Registry.graph instance is
     created during the full smoke analysis (counter proxy, audit-only).
  2. conservative   (P0#1): smoke net -> «нет» + per-transition breakdown;
     cycle p1→t1→p2→t2→p1 µ=(1,0) -> «да».
  3. loading state  (P2): before the first /state the step panel shows
     «Загрузка…», never «нет разрешённых переходов» (MutationObserver log).
  4. keyboard       (P1#6): Tab reaches .history-line (now a <button>) and
     Enter restores the step (current marking changes back).
  5. mobile375      (P1#5): scrollWidth <= innerWidth at 375x667 and 768x1024.
  6. resize re-fit  (P2): graph zoom changes (re-fit) after a window resize.
  7. hotkeys        (P2/FR-615): 1 -> net view, 2 -> home view, T -> theme cycle.

Screenshots + JSON digest: /e2e/screenshots/audit (host: docs/acceptance/audit).
Exits non-zero if any check fails.
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

# Консервативный цикл: каждая т — 1 вход / 1 выход, сумма меток = 1.
CYCLE_TEXT = """S = (P, T, I, O, µ),
P = {p1, p2}, T = {t1, t2},
I(t1) = {p1}, O(t1) = {p2},
I(t2) = {p2}, O(t2) = {p1},
µ = (1, 0)."""

# Registry-прокси (счётчик созданий инстансов) + журнал /state + MutationObserver
# над «заглушкой» step-панели. Только для аудита, не в e2e-контракт.
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
  const stateLog = { samples: [], stateResponses: [] };
  const _fetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '?';
    const t0 = performance.now();
    return _fetch(input, init).then((res) => {
      netlog.push({ url, status: res.status, ms: Math.round(performance.now() - t0) });
      if (url.includes('/state')) {
        stateLog.stateResponses.push({ t: Math.round(performance.now()), status: res.status });
      }
      return res;
    });
  };
  // Сэмплирование состояния step-панели раз в 50 мс: между появлением
  // «узлов: N» и ответом /state DOM #active-list не меняется, поэтому
  // последний сэмпл до /state = состояние в момент, когда stats уже есть.
  let lastSampleKey = "";
  const sampleNow = () => {
    const list = document.getElementById('active-list');
    const btns = list ? list.querySelectorAll('.btn-transition').length : -1;
    const mutedEl = list ? list.querySelector('.muted') : null;
    const muted = mutedEl ? mutedEl.textContent : null;
    const key = btns + '|' + muted;
    if (key !== lastSampleKey) {
      stateLog.samples.push({ t: Math.round(performance.now()), btns, muted });
      lastSampleKey = key;
    }
  };
  sampleNow();
  setInterval(sampleNow, 50);
  window.__audit = { sets, netlog, stateLog };
})();
"""

CONSERVATIVE_ROW_JS = """
() => {
  const rows = Array.from(document.querySelectorAll('#props tbody tr'));
  for (const tr of rows) {
    const name = tr.querySelector('td.props-name');
    if (name && name.textContent.trim() === 'Консервативная') {
      const v = tr.querySelector('td.props-value');
      return v ? v.textContent.trim() : null;
    }
  }
  return null;
}
"""

NET_LABELS_JS = "()" \
    " => (window.Registry && window.Registry.net)" \
    " ? window.Registry.net.$('node').map((n) => n.data('label')).sort() : []"


def shot(name: str, page, full: bool = True) -> str:
    p = SHOTS / name
    page.screenshot(path=str(p), full_page=full)
    return str(p)


def wait_analysis(page, node_count: int, timeout_ms: int = 120000) -> None:
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


def main() -> int:
    out: dict = {
        "base_url": BASE_URL,
        "console": [],
        "checks": {},
    }
    failures: list[str] = []

    def check(name: str, ok: bool, detail: dict) -> None:
        out["checks"][name] = {"ok": bool(ok), **detail}
        if not ok:
            failures.append(name)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)
        page.on(
            "console",
            lambda msg: out["console"].append(f"{msg.type}: {msg.text}")
            if msg.type in ("error", "warning")
            else None,
        )
        page.on("pageerror", lambda exc: out["console"].append(f"pageerror: {exc}"))

        # ---------- 1+2+3. Full smoke analysis: double-render, conservative, loading
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        t0 = page.evaluate("() => performance.now()")
        page.click("#btn-run-text")
        wait_analysis(page, 1503)
        t1 = page.evaluate("() => performance.now()")

        sets = page.evaluate("() => window.__audit.sets.slice()")
        graph_creates = [s for s in sets if s["key"] == "graph" and s["created"]]
        check(
            "double_render_p1_4",
            len(graph_creates) == 1,
            {
                "graph_instance_creates": len(graph_creates),
                "expected": 1,
                "registry_sets_graph": [s for s in sets if s["key"] == "graph"],
                "client_total_ms": round(t1 - t0, 1),
                "prev_client_total_ms": 2830.0,
            },
        )

        cons_smoke = page.evaluate(CONSERVATIVE_ROW_JS)
        check(
            "conservative_p0_smoke",
            cons_smoke is not None
            and cons_smoke.startswith("нет")
            and "t1: 2≠1" in cons_smoke,
            {"value": cons_smoke, "expected": "«нет» + разбивка t1: 2≠1"},
        )
        shot("50-p0-conservative-net-light.png", page)

        state_log = page.evaluate("() => window.__audit.stateLog")
        first_state_t = (
            state_log["stateResponses"][0]["t"] if state_log["stateResponses"] else None
        )
        pre = [s for s in state_log["samples"] if first_state_t is None or s["t"] < first_state_t]
        saw_loading = any(
            s["muted"] is not None and "Загрузка" in s["muted"] for s in pre
        )
        saw_fake_empty = any(
            s["muted"] is not None and "нет разрешённых" in s["muted"] for s in pre
        )
        check(
            "loading_state_p2",
            bool(pre) and saw_loading and not saw_fake_empty,
            {
                "samples_before_first_state": pre,
                "state_responses": state_log["stateResponses"],
                "saw_loading": saw_loading,
                "fake_empty_before_first_state": saw_fake_empty,
            },
        )
        shot("51-p2-loading-state.png", page, full=False)

        # ---------- 4. Keyboard: Tab -> .history-line, Enter restores step ----
        # два шага: m0 --t1--> m1 --t2--> m2
        page.locator("#active-list .btn-transition", has_text="t1").click()
        page.wait_for_function(
            "(label) => {"
            " const g = window.Registry && window.Registry.net;"
            " return !!g && g.$('node').some((n) => n.data('label') === label);"
            "}",
            arg="p1 (5)",
            timeout=15000,
        )
        labels_m1 = page.evaluate(NET_LABELS_JS)
        page.locator("#active-list .btn-transition", has_text="t2").click()
        page.wait_for_function(
            "(label) => {"
            " const g = window.Registry && window.Registry.net;"
            " return !!g && g.$('node').some((n) => n.data('label') === label);"
            "}",
            arg="p1 (4)",
            timeout=15000,
        )
        labels_m2 = page.evaluate(NET_LABELS_JS)

        page.evaluate("() => document.getElementById('btn-reset').focus()")
        reached = None
        for _ in range(40):
            page.keyboard.press("Tab")
            info = page.evaluate(
                "() => { const el = document.activeElement; if (!el) return null;"
                " const cls = typeof el.className === 'string' ? el.className : '';"
                " const cs = getComputedStyle(el);"
                " return { cls, ring: (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0)"
                " || cs.boxShadow !== 'none' };"
                " }"
            )
            if info and "history-line" in info["cls"]:
                reached = info
                break
        # Enter на сфокусированной первой строке истории -> goto m1
        page.keyboard.press("Enter")
        page.wait_for_function(
            "(label) => {"
            " const g = window.Registry && window.Registry.net;"
            " return !!g && g.$('node').some((n) => n.data('label') === label);"
            "}",
            arg="p1 (5)",
            timeout=15000,
        )
        labels_after_enter = page.evaluate(NET_LABELS_JS)
        check(
            "keyboard_p1_6",
            reached is not None
            and labels_after_enter == labels_m1
            and labels_m2 != labels_m1,
            {
                "tab_reached_history_line": bool(reached),
                "focus_ring": reached.get("ring") if reached else None,
                "labels_m2": labels_m2,
                "labels_after_enter": labels_after_enter,
                "labels_m1": labels_m1,
                "restored": labels_after_enter == labels_m1,
            },
        )
        shot("52-p1-keyboard-history.png", page, full=False)

        # ---------- 5. Mobile 375 / tablet 768 overflow -----------------------
        for width, height, tag in ((375, 667, "mobile375"), (768, 1024, "tablet768")):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(400)
            metrics = page.evaluate(
                "() => ({ scroll: document.documentElement.scrollWidth,"
                " inner: window.innerWidth, client: document.documentElement.clientWidth })"
            )
            check(
                f"overflow_{tag}_p1_5",
                metrics["scroll"] <= metrics["inner"],
                metrics,
            )
            shot(f"54-p1-{tag}.png" if width == 375 else f"55-p1-{tag}.png", page)

        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(300)

        # ---------- 6. Resize re-fit (zoom должен поменяться) ------------------
        zoom_before = page.evaluate(
            "() => (window.Registry && window.Registry.graph) ? window.Registry.graph.zoom() : null"
        )
        page.set_viewport_size({"width": 700, "height": 600})
        page.wait_for_timeout(700)  # debounce 200ms + запас
        zoom_after = page.evaluate(
            "() => (window.Registry && window.Registry.graph) ? window.Registry.graph.zoom() : null"
        )
        check(
            "resize_refit_p2",
            zoom_before is not None
            and zoom_after is not None
            and abs(zoom_after - zoom_before) > 1e-6
            and zoom_after < zoom_before,
            {"zoom_before": zoom_before, "zoom_after_700x600": zoom_after},
        )
        shot("56-p2-resize-fit.png", page)
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(300)

        # ---------- 7. Hotkeys 1 / 2 / T ---------------------------------------
        theme_before = page.evaluate("() => document.documentElement.dataset.theme")
        page.keyboard.press("2")
        page.wait_for_selector(".task-card", timeout=5000)
        home_ok = page.evaluate(
            "() => !!document.querySelector('.task-card') && getComputedStyle(document.querySelector('.home')).display !== 'none'"
        )
        page.keyboard.press("1")
        page.wait_for_selector("#input-text", state="visible", timeout=5000)
        net_ok = page.evaluate(
            "() => getComputedStyle(document.querySelector('.net-view')).display !== 'none'"
        )
        page.keyboard.press("t")
        page.wait_for_timeout(150)
        theme_after = page.evaluate("() => document.documentElement.dataset.theme")
        check(
            "hotkeys_p2",
            home_ok and net_ok and theme_after != theme_before,
            {
                "press_2_shows_home": home_ok,
                "press_1_shows_net": net_ok,
                "theme_before": theme_before,
                "theme_after_t": theme_after,
            },
        )
        shot("57-p2-hotkeys.png", page)

        ctx.close()

        # ---------- 2b. Консервативная сеть -> «да» ----------------------------
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.fill("#input-text", CYCLE_TEXT)
        page.click("#btn-run-text")
        wait_analysis(page, 2)
        cons_cycle = page.evaluate(CONSERVATIVE_ROW_JS)
        check(
            "conservative_p0_cycle_da",
            cons_cycle is not None and cons_cycle == "да",
            {"value": cons_cycle, "expected": "да"},
        )
        shot("53-p0-conservative-da.png", page)
        ctx.close()
        browser.close()

    out["console_clean"] = len(out["console"]) == 0

    digest_path = SHOTS / "audit_fixes.json"
    digest_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n[audit_fixes] digest -> {digest_path}", file=sys.stderr)
    if failures:
        print(f"[audit_fixes] FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("[audit_fixes] all checks passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
