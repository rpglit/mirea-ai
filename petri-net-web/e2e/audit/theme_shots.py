# Приёмочные скриншоты тем (итерация 3, фаза 2.2) → docs/acceptance/themes/.
# Пары light/dark (DoD): main, graph, props, report (+ все именованные темы для паритета).
# Запуск: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/theme_shots.py"

import sys
from pathlib import Path

sys.path.insert(0, "/e2e")

from playwright.sync_api import sync_playwright  # noqa: E402

from conftest import BASE_URL, analyze_via_text  # noqa: E402

OUT = Path("/e2e/screenshots/themes")
OUT.mkdir(parents=True, exist_ok=True)

THEMES = ["light", "dark", "tokyo-night", "catppuccin-mocha", "synthwave84"]


def switch_theme(page, theme: str) -> None:
    page.evaluate("localStorage.setItem('pn-theme', %r)" % theme)
    page.reload()
    page.wait_for_selector(".theme-select")
    actual = page.evaluate("() => document.documentElement.dataset.theme")
    assert actual == theme, f"ожидалась тема {theme}, получена {actual}"


def shot_report(page) -> None:
    page.goto(BASE_URL)
    page.click("button:has-text('Задание из практикума')")
    page.wait_for_selector(".task-card")
    page.click("button.tab:has-text('ЛСС')")
    page.locator(".task-card", has_text="TASK-LSS-14").first.locator(
        "button", has_text="Решить"
    ).click()
    page.wait_for_selector("#task-data")
    page.locator(".solver button.primary", has_text="Решить").click()
    page.wait_for_selector(".report .katex")


def main() -> None:
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.on(
            "console",
            lambda m: problems.append(f"{m.type}: {m.text}")
            if m.type in ("error", "warning")
            else None,
        )
        page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
        page.goto(BASE_URL)
        page.wait_for_selector(".theme-select")

        for theme in THEMES:
            switch_theme(page, theme)
            analyze_via_text(page)
            page.screenshot(path=str(OUT / f"main-{theme}.png"), full_page=True)
            page.click("#canvas-graph")
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / f"graph-{theme}.png"), full_page=True)
            page.locator("#props-panel").screenshot(path=str(OUT / f"props-{theme}.png"))
            shot_report(page)
            page.screenshot(path=str(OUT / f"report-{theme}.png"), full_page=True)
            print(f"{theme}: 4 скриншота")

        browser.close()

    print("console problems:", problems if problems else "none")
    print(f"всего PNG: {len(list(OUT.glob('*.png')))} в {OUT}")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
