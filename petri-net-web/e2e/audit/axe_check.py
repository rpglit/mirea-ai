# A11y-аудит: axe-core на 4 ключевых экранах (NFR-111, итерация 3, фаза 2.6).
# Экраны: «Сеть Петри» (main) и «Задание из практикума» (отчёт LSS-14) × light/dark.
# Критерий: 0 violations уровня critical/major; moderate/minor — в отчёт как
# замечания. Результаты: docs/acceptance/a11y/axe_*.json + axe_summary.json.
# Запуск (медленный, не в pytest): sudo docker compose run --rm e2e \
#     bash -lc "cd /e2e && python audit/axe_check.py"

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/e2e")

from playwright.sync_api import Page, sync_playwright  # noqa: E402

import vr  # noqa: E402

AXE_JS = "/opt/axe/node_modules/axe-core/axe.min.js"
OUT_DIR = Path("/e2e/screenshots/a11y")

CASES = [
    ("main-light", "light", vr.render_main),
    ("main-dark", "dark", vr.render_main),
    ("report-lss14-light", "light", vr.render_report_lss14),
    ("report-lss14-dark", "dark", vr.render_report_lss14),
]


# axe-core 4.10+ переименовал impact "major" -> "serious" (терминология WCAG).
# Критерий NFR-111 «0 critical и 0 major» = 0 critical + 0 major/serious.
MAJOR_IMPACTS = ("critical", "major", "serious")


def run_axe(page: Page) -> dict:
    page.add_script_tag(path=AXE_JS)
    return page.evaluate("() => window.axe.run({ reportVersion: 2 })")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "axe_core_version": None,
        "criterion": "0 violations уровня critical и major (axe-core 4.13: major = serious)",
        "screens": {},
    }
    blocked = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, theme, render in CASES:
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            try:
                vr.set_theme(page, theme)
                render(page)
                results = run_axe(page)
                summary["axe_core_version"] = results.get("testEngine", {}).get("name")
                (OUT_DIR / f"axe_{name}.json").write_text(
                    json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
                )
                counts: dict[str, int] = {}
                notable = []
                for v in results.get("violations", []):
                    impact = v.get("impact") or "none"
                    counts[impact] = counts.get(impact, 0) + 1
                    if impact in MAJOR_IMPACTS:
                        blocked = True
                        notable.append(
                            {
                                "rule": v.get("id"),
                                "impact": impact,
                                "description": v.get("description"),
                                "help": v.get("help"),
                                "tags": v.get("tags"),
                                "nodes": len(v.get("nodes", [])),
                                "targets": [n.get("target") for n in v.get("nodes", [])[:5]],
                            }
                        )
                page.screenshot(path=str(OUT_DIR / f"axe_{name}.png"), full_page=True)
                summary["screens"][name] = {"counts": counts, "notable": notable}
                print(
                    f"{name}: "
                    + ", ".join(f"{k}={c}" for k, c in counts.items() if c)
                    + ("  [BLOCKED]" if any(n for n in notable) else "")
                )
            finally:
                page.close()
        browser.close()
    summary["pass"] = not blocked
    (OUT_DIR / "axe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for name, screen in summary["screens"].items():
        for n in screen["notable"]:
            print(
                f"NOTABLE {name}: [{n['impact']}] {n['rule']} — {n['description']} "
                f"(nodes={n['nodes']}, targets={n['targets']})",
                file=sys.stderr,
            )
    print(f"axe summary: {OUT_DIR / 'axe_summary.json'}; pass={not blocked}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    sys.exit(main())
