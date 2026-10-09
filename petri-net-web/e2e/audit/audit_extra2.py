#!/usr/bin/env python3
"""Refined probes: event-loop block sampling, 375px overflow cause, deadlock UX,
transient 'no active transitions' state during the analysis pipeline.

Run: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_extra2.py"
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

    # ---------------- 1. event-loop block: fine-grained sampling ------------
    cat = {t["task_id"]: t for t in json.loads(api("GET", "/catalog")[2])}
    base = []
    for _ in range(5):
        _, ms, _ = api("GET", "/healthz", timeout=5)
        base.append(round(ms, 1))
    # three different heavy solves with unique cache keys, 10 ms sampling
    block_runs = []
    for task_id in ("TASK-LSS-20", "TASK-LSS-10", "TASK-PN-08"):
        data = dict(cat[task_id]["prefill"] or {})
        data["audit_fresh"] = int(time.time() * 1000000)
        probe: dict = {}

        def solve_bg(tid=task_id, d=data):
            st, ms, raw = api("POST", "/solve", {"task_id": tid, "data": d})
            probe.update({"status": st, "ms": round(ms, 1)})

        th = threading.Thread(target=solve_bg)
        th.start()
        time.sleep(0.03)
        samples = []
        while th.is_alive():
            t0 = time.perf_counter()
            try:
                urllib.request.urlopen(BASE_URL + "/healthz", timeout=5)
                samples.append(round((time.perf_counter() - t0) * 1000, 1))
            except Exception as e:  # noqa: BLE001
                samples.append(f"err:{type(e).__name__}")
            time.sleep(0.01)
        th.join()
        block_runs.append(
            {
                "task": task_id,
                "solve_ms": probe.get("ms"),
                "max_probe_ms": max((s for s in samples if isinstance(s, (int, float))), default=0),
                "median_probe_ms": (
                sorted(s for s in samples if isinstance(s, (int, float)))[len(samples) // 2]
                if samples else 0),
                "n_samples": len(samples),
                "worsened_vs_baseline": (
                    max((s for s in samples if isinstance(s, (int, float))), default=0)
                    > max(base) * 3),
            }
        )
    out["sections"]["event_loop_block_sampled"] = {
        "healthz_baseline_ms": base,
        "runs": block_runs,
    }

    # ---------------- 2. 375px overflow cause --------------------------------
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 375, "height": 667})
        page = ctx.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.click("#btn-run-text")
        page.wait_for_function(
            "() => { const s = document.getElementById('graph-stats');"
            " return !!s && s.textContent.includes('узлов: 1503'); }",
            timeout=120000,
        )
        page.wait_for_function(
            "() => document.querySelectorAll('#active-list .btn-transition').length > 0",
            timeout=60000,
        )
        diag = page.evaluate(
            "() => { const vw = document.documentElement.clientWidth;"
            " const wide = [];"
            " document.querySelectorAll('*').forEach((el) => {"
            "   const r = el.getBoundingClientRect();"
            "   if (r.width > vw + 2) wide.push({sel: (el.id ? '#' + el.id : el.tagName.toLowerCase())"
            "     + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/)[0] : ''),"
            "     w: Math.round(r.width)});"
            "   else if (el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0) {"
            "     wide.push({sel: (el.id ? '#' + el.id : el.tagName.toLowerCase())"
            "       + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/)[0] : ''),"
            "       w: 'inner-overflow:' + el.scrollWidth + '>' + Math.round(r.width)});"
            "   } });"
            " const bodyKids = [];"
            " Array.from(document.body.children).forEach((el) => bodyKids.push({"
            "   sel: (el.id ? '#' + el.id : el.tagName.toLowerCase()),"
            "   offsetW: el.offsetWidth, scrollW: el.scrollWidth }));"
            " return { vw, pageScrollW: document.documentElement.scrollWidth, wide: wide.slice(0, 15), bodyKids };"
            " }"
        )
        page.screenshot(path=str(SHOTS / "20-mobile375-analysis.png"), full_page=True)
        out["sections"]["mobile375_cause"] = diag
        ctx.close()

        # ---------------- 3/4. deadlock UX + transient empty state -----------
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.click("#btn-run-text")
        # capture the TRANSIENT state: stats visible but active list still empty
        page.wait_for_function(
            "() => { const s = document.getElementById('graph-stats');"
            " return !!s && s.textContent.includes('узлов: 1503'); }",
            timeout=120000,
        )
        transient = page.evaluate(
            "() => ({ active: document.querySelectorAll('#active-list .btn-transition').length,"
            " muted: document.querySelector('#active-list .muted') ? document.querySelector('#active-list .muted').textContent : null,"
            " btnStepDisabled: document.getElementById('btn-step').disabled })"
        )
        page.screenshot(path=str(SHOTS / "21-transient-no-active.png"))
        out["sections"]["transient_state_after_stats"] = transient
        page.wait_for_function(
            "() => document.querySelectorAll('#active-list .btn-transition').length > 0",
            timeout=60000,
        )
        # now click a deadlocked (red) node
        dl_info = page.evaluate(
            "() => { const g = window.Registry.graph; const dl = g.nodes('[?deadlock]');"
            " if (!dl.length) return {found: false};"
            " dl[0].emit('tap'); return {found: true, count: dl.length, label: dl[0].data('label')}; }"
        )
        page.wait_for_function(
            "() => document.querySelectorAll('#active-list .btn-transition').length === 0",
            timeout=30000,
        )
        dl_state = page.evaluate(
            "() => ({ active: document.querySelectorAll('#active-list .btn-transition').length,"
            " muted: document.querySelector('#active-list .muted') ? document.querySelector('#active-list .muted').textContent : null,"
            " btnStepDisabled: document.getElementById('btn-step').disabled,"
            " status: document.getElementById('status-line').textContent })"
        )
        page.screenshot(path=str(SHOTS / "22-deadlock-state.png"))
        out["sections"]["deadlock_state"] = {"deadlock_nodes": dl_info, "state": dl_state}
        ctx.close()
        browser.close()

    p = SHOTS / "audit_extra2.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
