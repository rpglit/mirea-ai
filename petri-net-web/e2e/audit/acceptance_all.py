# Приёмка итерации 3 (фаза 4): полный прогон всех 71 задач через веб-интерфейс
# в обеих темах (light/dark) + приёмочные артефакты.
#
# Запуск: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/acceptance_all.py"
# (app должен быть up; опц. ACCEPTANCE_FILTER=TASK-FA-03,TASK-PN-05 — подмножество)
#
# Артефакты (docs/acceptance/iteration3/):
#   reports/<task_id>-<theme>.json   — ответ POST /solve {task_id, data:{}}
#   screenshots/<task_id>-<theme>.png — точечные скриншоты (SHOOT)
#   acceptance_summary.json, acceptance_table.md, acceptance_details.json

import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
OUT = Path("/e2e/screenshots/iteration3")
REPORTS = OUT / "reports"
SHOTS = OUT / "screenshots"
THEMES = ["light", "dark"]
SOLVE_TIMEOUT_MS = 60_000
WAIT_TIMEOUT_MS = 20_000

# точечные скриншоты: (task_id, theme)
SHOOT = {
    ("TASK-PN-05", "light"),
    ("TASK-PN-05", "dark"),
    ("TASK-LSS-14", "light"),
    ("TASK-LSS-14", "dark"),
    ("TASK-FA-03", "light"),
    ("TASK-FA-03", "dark"),
    ("TASK-LSS-23", "dark"),
    ("TASK-PN-27", "light"),
}

FILTER = os.environ.get("ACCEPTANCE_FILTER")
FILTER_IDS = {s.strip() for s in FILTER.split(",")} if FILTER else None


def get_catalog():
    with urllib.request.urlopen(BASE_URL + "/catalog", timeout=30) as resp:
        tasks = json.load(resp)
    if not FILTER_IDS:
        assert len(tasks) == 71, f"ожидалось 71 задача в каталоге, получено {len(tasks)}"
    if FILTER_IDS:
        tasks = [t for t in tasks if t["task_id"] in FILTER_IDS]
    return tasks


def post_solve(task_id):
    req = urllib.request.Request(
        BASE_URL + "/solve",
        data=json.dumps({"task_id": task_id, "data": {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def expected_automaton_keys(answer):
    """FA: какие ключи window.Registry обязаны быть смонтированы по answer."""
    keys = []
    graph = answer.get("graph")
    if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
        keys.append("automaton")
    mealy = answer.get("mealy")
    if isinstance(mealy, dict) and isinstance(mealy.get("graph"), dict):
        keys.append("mealy")
    for k in ("r1", "r2"):
        sub = answer.get(k)
        if isinstance(sub, dict) and isinstance(sub.get("graph"), dict):
            keys.append(k)
    return keys


def tex_paths(report):
    """Все TeX-поля в JSON отчёта (для обоснования отсутствия .katex)."""
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if (k.endswith("_tex") or k == "tex") and isinstance(v, str) and v.strip():
                    found.append(f"{path}.{k}")
                else:
                    walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(report, "$")
    return found


def run_pair(browser, task, theme):
    task_id, group = task["task_id"], task["group"]
    res = {
        "task_id": task_id,
        "group": group,
        "theme": theme,
        "ok": False,
        "solve_ms": None,
        "katex_count": None,
        "formula_fallbacks": None,
        "katex_errors": None,
        "answer_block": None,
        "fa_expected": None,
        "page_errors": [],
        "console_errors": [],
        "errors": [],
        "screenshot": None,
    }
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    report_json = None
    try:
        page.on("pageerror", lambda exc: res["page_errors"].append(str(exc)))
        page.on(
            "console",
            lambda m: res["console_errors"].append(m.text) if m.type == "error" else None,
        )

        # FA: JSON заранее — нужны ожидаемые ключи canvas (вычисление тривиальное)
        if group == "FA":
            report_json = post_solve(task_id)

        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT_MS)
        page.wait_for_selector(".theme-select", timeout=WAIT_TIMEOUT_MS)
        page.evaluate("t => localStorage.setItem('pn-theme', t)", theme)
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=WAIT_TIMEOUT_MS)
        page.wait_for_selector(".theme-select", timeout=WAIT_TIMEOUT_MS)
        actual = page.evaluate("() => document.documentElement.dataset.theme")
        if actual != theme:
            res["errors"].append(f"тема: ожидалась {theme}, получена {actual}")
            return res

        page.click("header nav button:has-text('Задание из практикума')")
        page.wait_for_selector(".task-card", timeout=WAIT_TIMEOUT_MS)
        card = page.locator(".task-card", has_text=task_id)
        if card.count() == 0:
            res["errors"].append("карточка задачи не найдена")
            return res
        card.first.locator("button", has_text="Решить").click()
        page.wait_for_selector("#task-data", timeout=WAIT_TIMEOUT_MS)

        t0 = time.monotonic()
        page.locator(".solver button.primary", has_text="Решить").click()
        page.wait_for_selector(".report", timeout=SOLVE_TIMEOUT_MS)
        res["solve_ms"] = round((time.monotonic() - t0) * 1000)

        report_text = page.locator(".report").inner_text()
        res["katex_count"] = page.locator(".report .katex").count()
        res["formula_fallbacks"] = page.locator(".report .formula__fallback").count()
        res["katex_errors"] = page.locator(".report .katex-error").count()
        res["answer_block"] = page.locator(".report h3.report-block", has_text="Ответ").count()

        # (a) заголовок отчёта
        if f"Отчёт по {task_id}" not in report_text:
            res["errors"].append(f"«Отчёт по {task_id}» не найден в .report")
        # (b) все формулы отрендерились
        if res["formula_fallbacks"]:
            res["errors"].append(f"formula__fallback: {res['formula_fallbacks']}")
        # (c) pageerror
        if res["page_errors"]:
            res["errors"].append("pageerror: " + " | ".join(res["page_errors"][:5]))
        # (d) LSS: .katex (absence допускается — фиксируется)
        if group == "LSS" and res["katex_count"] == 0:
            res["no_katex"] = True
        # (e) FA: canvas автомата
        if group == "FA":
            exp = expected_automaton_keys(report_json.get("answer", {}))
            res["fa_expected"] = exp
            if exp:
                page.wait_for_function(
                    "keys => Object.keys(keys).every(k => window.Registry && window.Registry[k] !== null)",
                    arg={k: True for k in exp},
                    timeout=WAIT_TIMEOUT_MS,
                )
            for k in exp:
                mounted = page.evaluate("k => window.Registry && window.Registry[k] !== null", k)
                if not mounted:
                    res["errors"].append(f"FA: window.Registry.{k} не смонтирован (ожидался {exp})")
        # (f) PN: нет katex-ошибок, блок «Ответ» есть
        if group == "PN":
            if res["katex_errors"]:
                res["errors"].append(f"PN: katex-error: {res['katex_errors']}")
            if res["answer_block"] == 0:
                res["errors"].append("PN: блок «Ответ» отсутствует")

        if not res["errors"]:
            res["ok"] = True

        # точечный скриншот
        if (task_id, theme) in SHOOT and res["ok"]:
            path = SHOTS / f"{task_id}-{theme}.png"
            page.screenshot(path=str(path), full_page=True)
            res["screenshot"] = f"screenshots/{task_id}-{theme}.png"
    except PWTimeoutError as exc:
        res["errors"].append(f"timeout: {exc}")
    except Exception as exc:  # noqa: BLE001 — фиксируем любой сбой пары
        res["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        # отчёт POST /solve {task_id, data:{}} → артефакт
        try:
            if report_json is None:
                report_json = post_solve(task_id)
            path = REPORTS / f"{task_id}-{theme}.json"
            path.write_text(json.dumps(report_json, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            res["errors"].append(f"сохранение отчёта POST /solve: {type(exc).__name__}: {exc}")
        # LSS без .katex: обоснование из JSON
        if res.get("no_katex"):
            tex = tex_paths(report_json) if report_json else []
            res["no_katex_reason"] = (
                "в JSON отчёта нет TeX-полей (ответ — только текст/числа)"
                if not tex
                else f"в JSON есть TeX ({', '.join(tex[:4])}), но в DOM .katex нет — баг рендера"
            )
        if not res["ok"]:
            try:
                fail_path = SHOTS / f"{task_id}-{theme}-FAIL.png"
                page.screenshot(path=str(fail_path), full_page=True)
                res["screenshot"] = f"screenshots/{task_id}-{theme}-FAIL.png"
            except Exception:  # noqa: BLE001
                pass
        page.close()
    return res


def p95(values):
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def build_table(tasks, by_id):
    lines = [
        "# Приёмка итерации 3 — все 71 задача × 2 темы (light/dark)",
        "",
        f"Прогон: {BASE_URL}, Playwright headless, fresh-страница на пару.",
        "",
        "| task_id | group | light | dark | отчёт |",
        "|---|---|---|---|---|",
    ]
    for t in tasks:
        tid, group = t["task_id"], t["group"]
        cells = {}
        for theme in THEMES:
            r = by_id.get(tid, {}).get(theme)
            if r is None:
                cells[theme] = "—"
            elif r["ok"]:
                cells[theme] = f"OK ({r['solve_ms']} ms)"
            else:
                cells[theme] = f"FAIL ({'; '.join(r['errors'][:2])})"
        links = " · ".join(
            f"[{th}](reports/{tid}-{th}.json)" if (REPORTS / f"{tid}-{th}.json").exists() else f"(нет: {tid}-{th}.json)"
            for th in THEMES
        )
        lines.append(f"| {tid} | {group} | {cells['light']} | {cells['dark']} | {links} |")
    return "\n".join(lines) + "\n"


def main():
    tasks = get_catalog()
    REPORTS.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    pairs = [(t, theme) for t in tasks for theme in THEMES]
    total = len(pairs)
    print(f"catalog: {len(tasks)} задач; пар: {total}", flush=True)

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for idx, (task, theme) in enumerate(pairs, 1):
                res = run_pair(browser, task, theme)
                results.append(res)
                status = "OK" if res["ok"] else "FAIL"
                t_ms = f"{res['solve_ms']} ms" if res["solve_ms"] is not None else "n/a"
                print(f"[{idx}/{total}] {res['task_id']} {theme} {status} {t_ms}"
                      + ("" if res["ok"] else " :: " + "; ".join(res["errors"][:3])), flush=True)
        finally:
            browser.close()

    ok = sum(1 for r in results if r["ok"])
    failed = [
        {
            "task_id": r["task_id"],
            "theme": r["theme"],
            "reason": "; ".join(r["errors"]),
            "errors": r["errors"],
            "page_errors": r["page_errors"],
            "console_errors": r["console_errors"][:20],
        }
        for r in results
        if not r["ok"]
    ]
    no_katex_lss = [
        {
            "task_id": r["task_id"],
            "theme": r["theme"],
            "reason": r.get("no_katex_reason", ""),
        }
        for r in results
        if r.get("no_katex")
    ]
    timings = [r["solve_ms"] for r in results if r["solve_ms"] is not None]
    screenshots = sorted(r["screenshot"] for r in results if r["screenshot"])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": BASE_URL,
        "total": total,
        "ok": ok,
        "failed": failed,
        "no_katex_lss": no_katex_lss,
        "timings": {
            "n": len(timings),
            "min": min(timings) if timings else None,
            "max": max(timings) if timings else None,
            "p95": p95(timings) if timings else None,
        },
        "screenshots": screenshots,
    }
    (OUT / "acceptance_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (OUT / "acceptance_details.json").write_text(
        json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    by_id = {}
    for r in results:
        by_id.setdefault(r["task_id"], {})[r["theme"]] = r
    (OUT / "acceptance_table.md").write_text(build_table(tasks, by_id), encoding="utf-8")

    print(
        f"\nИТОГ: {ok}/{total} OK; FAIL: {len(failed)}; "
        f"timings min/max/p95 = {summary['timings']['min']}/{summary['timings']['max']}/{summary['timings']['p95']} ms; "
        f"LSS без .katex: {len(no_katex_lss)}; скриншотов: {len(screenshots)}",
        flush=True,
    )
    for f in failed:
        print(f"  FAIL {f['task_id']} {f['theme']}: {f['reason'][:300]}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
