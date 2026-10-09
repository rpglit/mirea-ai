#!/usr/bin/env python3
"""Capture user-visible strings of the «Задание из практикума» reports (LSS + FA)
for the terminology audit. Run:
    sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_terms.py"
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
SHOTS = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots")) / "audit"
SHOTS.mkdir(parents=True, exist_ok=True)


def main() -> None:
    out: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1400, "height": 1600}).new_page()
        page.goto(BASE_URL)
        page.click("button:has-text('Задание из практикума')")
        page.wait_for_selector(".task-card")

        for task_id, shot_name in (
            ("TASK-LSS-10", "40-report-lss10.png"),
            ("TASK-FA-07", "41-report-fa07.png"),
            ("TASK-PN-09", "42-report-pn09.png"),
        ):
            page.locator(".task-card", has_text=task_id).first.locator("button", has_text="Решить").click()
            page.wait_for_selector("#task-data")
            page.locator(".solver button.primary", has_text="Решить").click()
            page.wait_for_selector(".report")
            page.wait_for_timeout(300)
            out[task_id] = {
                "given_keys": page.evaluate(
                    "() => Array.from(document.querySelectorAll('.given-dl dt')).map((e) => e.textContent)"
                ),
                "answer_labels": page.evaluate(
                    "() => Array.from(document.querySelectorAll('.answer-key')).map((e) => e.textContent)"
                ),
                "report_text": page.inner_text(".report"),
            }
            page.screenshot(path=str(SHOTS / shot_name), full_page=True)
            # close and pick next
            page.click(".solver button:has-text('Закрыть')")
            page.wait_for_timeout(200)
        browser.close()

    p = SHOTS / "audit_terms.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in out.items():
        print(f"== {k} ==")
        print("given keys:", v["given_keys"])
        print("answer labels:", v["answer_labels"])


if __name__ == "__main__":
    main()
