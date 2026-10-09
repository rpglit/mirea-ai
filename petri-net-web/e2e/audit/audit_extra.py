#!/usr/bin/env python3
"""Standalone follow-up audit probes (NOT pytest).

Run: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_extra.py"

Probes:
  1. event-loop blocking of async /solve (fresh, non-cached heavy solve + /healthz probes)
  2. which elements overflow the 375px viewport
  3. full keyboard Tab order from the top of the document
  4. inhibitor-arc loss when a session is re-opened from history (P1 visual proof)
  5. deadlock UX state: goto a deadlocked node -> step panel empty state
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots")) / "audit"
SHOTS.mkdir(parents=True, exist_ok=True)

INIT_JS = r"""
(() => {
  window.__audit = { sets: [] };
  let _reg = null;
  Object.defineProperty(window, 'Registry', {
    configurable: true,
    get() { return _reg; },
    set(v) {
      _reg = new Proxy(v, {
        set(t, k, val) { t[k] = val; window.__audit.sets.push(String(k) + '=' + (val ? 'cy' : 'null')); return true; },
      });
    },
  });
})();
"""

INH_FORM = {
    "places": ["p1", "p2"],
    "transitions": ["t1", "t2"],
    "arcs": [
        {"source": "p2", "target": "t1", "weight": 1, "direction": "input"},
        {"source": "t1", "target": "p1", "weight": 1, "direction": "output"},
        {"source": "p1", "target": "t2", "weight": 1, "direction": "input"},
        {"source": "t2", "target": "p2", "weight": 1, "direction": "output"},
        {"source": "p1", "target": "t1", "direction": "inhibitor"},
        {"source": "p2", "target": "t2", "direction": "inhibitor"},
    ],
    "initial_marking": {"p1": 0, "p2": 1},
}

SMOKE_TEXT = """S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3)."""


def api(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (time.perf_counter() - t0) * 1000, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (time.perf_counter() - t0) * 1000, raw


def main() -> None:
    out: dict = {"base_url": BASE_URL, "sections": {}}

    # ---------------- 1. event-loop blocking (fresh solve) -------------------
    cat = {t["task_id"]: t for t in json.loads(api("GET", "/catalog")[2])}
    lss20 = dict(cat["TASK-LSS-20"]["prefill"])
    lss20["audit_fresh"] = int(time.time())  # unique key -> not in the LRU
    probe: dict = {}

    def solve_bg():
        st, ms, raw = api("POST", "/solve", {"task_id": "TASK-LSS-20", "data": lss20})
        probe.update({"status": st, "ms": round(ms, 1)})

    th = threading.Thread(target=solve_bg)
    th.start()
    time.sleep(0.12)
    probes = []
    deadline = time.time() + 12
    while time.time() < deadline and th.is_alive():
        t0 = time.perf_counter()
        try:
            urllib.request.urlopen(BASE_URL + "/healthz", timeout=5)
            probes.append(round((time.perf_counter() - t0) * 1000, 1))
        except Exception as e:  # noqa: BLE001
            probes.append(f"err:{type(e).__name__}")
        time.sleep(0.08)
    th.join()
    out["sections"]["event_loop_block_fresh"] = {
        "solve": probe,
        "healthz_probes_ms_during_solve": probes,
        "blocked": any(isinstance(p, float) and p > 250 for p in probes),
    }

    # ---------------- 2-5 browser probes -------------------------------------
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        # --- 2. 375px overflow elements ---
        ctx = browser.new_context(viewport={"width": 375, "height": 667})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.click("#btn-run-text")
        page.wait_for_function(
            "() => { const s = document.getElementById('graph-stats');"
            " return !!s && s.textContent.includes('узлов: 1503'); }",
            timeout=120000,
        )
        page.wait_for_timeout(300)
        overflow = page.evaluate(
            "() => { const vw = document.documentElement.clientWidth; const res = [];"
            " document.querySelectorAll('*').forEach((el) => {"
            "   const r = el.getBoundingClientRect();"
            "   if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {"
            "     let sel = el.tagName.toLowerCase();"
            "     if (el.id) sel += '#' + el.id;"
            "     else if (typeof el.className === 'string' && el.className.trim()) sel += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');"
            "     res.push({sel, w: Math.round(r.width), left: Math.round(r.left), right: Math.round(r.right)});"
            "   } });"
            " return res.sort((a,b) => b.w - a.w).slice(0, 12); }"
        )
        page.screenshot(path=str(SHOTS / "10-mobile375-overflow.png"), full_page=True)
        out["sections"]["mobile375_overflow_elements"] = {
            "scrollWidth": page.evaluate("() => document.documentElement.scrollWidth"),
            "clientWidth": page.evaluate("() => document.documentElement.clientWidth"),
            "elements": overflow,
        }
        ctx.close()

        # --- 3. full keyboard Tab order from the top ---
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        seq = []
        for i in range(45):
            page.keyboard.press("Tab")
            info = page.evaluate(
                "() => { const el = document.activeElement; if (!el) return null;"
                " if (el === document.body) return {sel: '(body)'};"
                " if (!el.__auditFid) { el.__auditFid = Math.random().toString(36).slice(2); }"
                " const cs = getComputedStyle(el);"
                " let sel = el.tagName.toLowerCase();"
                " if (el.id) sel += '#' + el.id;"
                " else if (typeof el.className === 'string' && el.className.trim()) sel += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');"
                " return {fid: el.__auditFid, sel, ring: (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || cs.boxShadow !== 'none',"
                " text: (el.textContent || '').trim().slice(0, 20)}; }"
            )
            if info is None:
                break
            if info.get("sel") == "(body)":
                continue
            if info.get("fid") and any(s.get("fid") == info["fid"] for s in seq):
                break  # full loop
            seq.append(info)
        out["sections"]["keyboard_tab_order_full"] = {
            "count": len(seq),
            "sequence": [ {k: s[k] for k in ("sel", "ring", "text") if k in s} for s in seq ],
            "first_ten": [s["sel"] for s in seq[:10]],
        }
        page.screenshot(path=str(SHOTS / "11-keyboard-top.png"))
        ctx.close()

        # --- 4. inhibitor loss on session re-open ---
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.click("#tab-form")
        page.fill("#form-places", "p1, p2")
        page.fill("#form-transitions", "t1, t2")
        # row 1: input p2 -> t1
        page.locator(".arc-row").nth(0).locator(".arc-source").fill("p2")
        page.locator(".arc-row").nth(0).locator(".arc-target").fill("t1")
        page.click("#btn-add-arc")
        # row 2: output t1 -> p1
        r = page.locator(".arc-row").nth(1)
        r.locator("select").select_option("output")
        r.locator(".arc-source").fill("t1")
        r.locator(".arc-target").fill("p1")
        page.click("#btn-add-arc")
        r = page.locator(".arc-row").nth(2)
        r.locator("select").select_option("input")
        r.locator(".arc-source").fill("p1")
        r.locator(".arc-target").fill("t2")
        page.click("#btn-add-arc")
        r = page.locator(".arc-row").nth(3)
        r.locator("select").select_option("output")
        r.locator(".arc-source").fill("t2")
        r.locator(".arc-target").fill("p2")
        page.click("#btn-add-arc")
        r = page.locator(".arc-row").nth(4)
        r.locator("select").select_option("inhibitor")
        r.locator(".arc-source").fill("p1")
        r.locator(".arc-target").fill("t1")
        page.click("#btn-add-arc")
        r = page.locator(".arc-row").nth(5)
        r.locator("select").select_option("inhibitor")
        r.locator(".arc-source").fill("p2")
        r.locator(".arc-target").fill("t2")
        page.fill("#form-marking", "0, 1")
        page.click("#btn-run-form")
        page.wait_for_function(
            "() => { const s = document.getElementById('graph-stats'); return !!s && s.textContent.includes('узлов:'); }",
            timeout=60000,
        )
        inh_before = page.evaluate(
            "() => { const c = window.Registry.net; return c ? c.edges('[direction = \"inhibitor\"]').length : -1; }"
        )
        page.screenshot(path=str(SHOTS / "12-inhibitor-before.png"))
        # open history and re-click the current session
        page.click("#btn-sessions")
        page.wait_for_selector("#sessions-list .session-item")
        page.locator("#sessions-list .session-item").first.click()
        page.wait_for_function(
            "() => { const c = window.Registry.net; return c && c.$('node').length >= 4; }",
            timeout=60000,
        )
        page.wait_for_timeout(400)
        inh_after = page.evaluate(
            "() => { const c = window.Registry.net; return c ? c.edges('[direction = \"inhibitor\"]').length : -1; }"
        )
        caption = page.evaluate(
            "() => { const els = document.querySelectorAll('.canvas-caption'); for (const e of els) if (e.textContent.includes('ингибитор')) return e.textContent; return null; }"
        )
        page.screenshot(path=str(SHOTS / "13-inhibitor-after-reopen.png"))
        out["sections"]["inhibitor_restore"] = {
            "inhibitor_edges_initial": inh_before,
            "inhibitor_edges_after_reopen": inh_after,
            "caption_mentions_inhibitor": bool(caption),
            "bug": inh_before > 0 and inh_after == 0,
        }
        ctx.close()

        # --- 5. deadlock UX state ---
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.add_init_script(INIT_JS)
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.click("#btn-run-text")
        page.wait_for_function(
            "() => { const s = document.getElementById('graph-stats'); return !!s && s.textContent.includes('узлов: 1503'); }",
            timeout=120000,
        )
        # find a deadlock node (red) in the graph canvas and click it
        clicked = page.evaluate(
            "() => { const g = window.Registry.graph; if (!g) return false;"
            " const dl = g.nodes('[?deadlock]'); if (dl.length === 0) return false;"
            " dl[0].emit('tap'); return true; }"
        )
        page.wait_for_timeout(600)
        state = page.evaluate(
            "() => ({ active: document.querySelectorAll('#active-list .btn-transition').length,"
            " muted: document.querySelector('#active-list .muted') ? document.querySelector('#active-list .muted').textContent : null,"
            " btnStepDisabled: document.getElementById('btn-step').disabled })"
        )
        page.screenshot(path=str(SHOTS / "14-deadlock-state.png"))
        out["sections"]["deadlock_state"] = {"clicked_deadlock_node": clicked, "state": state}
        ctx.close()

        browser.close()

    p = SHOTS / "audit_extra.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n[audit_extra] digest -> {p}", flush=True)


if __name__ == "__main__":
    main()
