#!/usr/bin/env python3
"""Deterministic check: inhibitor arcs lost when a session is re-opened from history.

Run: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_inhibitor.py"
The session is created through the UI (JSON channel, named), its id is then found
via the API; the UI history is re-opened and inhibitor edge counts are compared.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots")) / "audit"
SHOTS.mkdir(parents=True, exist_ok=True)

NAME = "audit-inh-ui"

INH_JSON = {
    "places": ["p1", "p2"],
    "transitions": ["t1", "t2"],
    "inputs": {"t1": {"p2": 1}, "t2": {"p1": 1}},
    "outputs": {"t1": {"p1": 1}, "t2": {"p2": 1}},
    "inhibitors": {"t1": ["p1"], "t2": ["p2"]},
    "initial_marking": {"p1": 0, "p2": 1},
}


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:  # noqa: BLE001
        return e.code, json.loads(e.read() or b"null")


def main() -> None:
    out: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")

        # 1) create the session through the UI
        page.fill("#session-name", NAME)
        page.click("#tab-json")
        page.fill("#input-json", json.dumps(INH_JSON, sort_keys=True))
        page.click("#btn-run-json")
        page.wait_for_function(
            "() => { const c = window.Registry.net; return c && c.$('node').length === 4; }",
            timeout=60000,
        )
        before = page.evaluate(
            "() => { const c = window.Registry.net;"
            " const edges = c.edges().map((e) => e.data('direction'));"
            " const caps = Array.from(document.querySelectorAll('.canvas-caption')).map((e) => e.textContent);"
            " return { nodes: c.$('node').length, edges, inhibitor: edges.filter((d) => d === 'inhibitor').length,"
            " captions: caps, badge: (document.getElementById('session-badge')||{}).textContent };"
            " }"
        )
        page.screenshot(path=str(SHOTS / "30-inh-created.png"))

        # 2) find the session id via the API (fresh list)
        st, sessions = api("GET", "/sessions?limit=10")
        mine = [s for s in sessions if s.get("name") == NAME]
        if not mine:
            raise SystemExit(f"session {NAME} not found in /sessions: {sessions[:3]}")
        sid = mine[0]["session_id"]
        out["session"] = {"id": sid}
        st, full = api("GET", f"/sessions/{sid}")
        out["get_session_has_inhibitors"] = "inhibitors" in full
        out["get_session_fields"] = sorted(full.keys())

        # mark the current net instance so we can detect the re-render after reopen
        page.evaluate("() => { if (window.Registry.net) window.Registry.net.__auditMark = true; }")
        # re-open from history: wait for OUR session in the (fresh) list
        page.click("#btn-sessions")
        page.wait_for_selector(f'#sessions-list .session-item[data-session-id="{sid}"]', timeout=15000)
        page.click(f'#sessions-list .session-item[data-session-id="{sid}"]')
        page.wait_for_function(
            "() => { const c = window.Registry.net;"
            " return c && c.__auditMark !== true && c.$('node').length === 4; }",
            timeout=60000,
        )
        page.wait_for_timeout(500)
        after = page.evaluate(
            "() => { const c = window.Registry.net;"
            " const edges = c.edges().map((e) => e.data('direction'));"
            " const caps = Array.from(document.querySelectorAll('.canvas-caption')).map((e) => e.textContent);"
            " return { nodes: c.$('node').length, edges, inhibitor: edges.filter((d) => d === 'inhibitor').length,"
            " captions: caps };"
            " }"
        )
        page.screenshot(path=str(SHOTS / "31-inh-after-reopen.png"))
        browser.close()

    out["before_reopen"] = before
    out["after_reopen"] = after
    out["bug_confirmed"] = before["inhibitor"] > 0 and after["inhibitor"] == 0
    p = SHOTS / "audit_inhibitor.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    api("DELETE", f"/sessions/{sid}")


if __name__ == "__main__":
    main()
