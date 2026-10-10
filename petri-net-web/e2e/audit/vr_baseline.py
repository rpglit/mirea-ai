# Фиксация VR-бэйджей (E2E-12): main + report-lss14 × light/dark →
# docs/acceptance/vr-baseline/ (монтируется в контейнере как /e2e/screenshots).
# Запуск: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/vr_baseline.py"

import sys
from pathlib import Path

sys.path.insert(0, "/e2e")

from playwright.sync_api import sync_playwright  # noqa: E402

import vr  # noqa: E402

CASES = [
    ("main-light", "light", vr.render_main),
    ("main-dark", "dark", vr.render_main),
    ("report-lss14-light", "light", vr.render_report_lss14),
    ("report-lss14-dark", "dark", vr.render_report_lss14),
]


def shoot(browser, name: str, theme: str, render) -> Path:
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        vr.set_theme(page, theme)
        render(page)
        path = vr.BASELINES_DIR / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
    finally:
        page.close()
    return path


def main() -> None:
    vr.BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        paths = [shoot(browser, name, theme, render) for name, theme, render in CASES]
        browser.close()
    for path in paths:
        print(f"baseline {path.name}: {path.stat().st_size} байт")


if __name__ == "__main__":
    main()
