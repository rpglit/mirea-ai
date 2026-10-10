# Perf-аудит (NFR-112, ADR-0012, итерация 3, фаза 2.6). Замеры — медиана из 3:
#  (a) полный browser-сценарий smoke-сети (goto → parse → анализ → граф
#      отрендерен, включая загрузку страницы) — бюджет ≤ 5 с (ADR-0012);
#  (b) POST /solve TASK-LSS-10 через HTTP API — бюджет ≤ 10 с (NFR-101);
#  (c) /healthz во время solve (из браузера; первые 5 fetch — метод задания,
#      далее дискретная выборка ~каждые 20 мс до конца solve — метод
#      audit_extra2) — бюджет p95 < 50 мс (FR-607).
# Для (c) solve принудительно холодный: в data уникальный ключ (LRU-кэш
# solve не попадает) — метод audit_extra2 («audit_fresh»).
# Результат: docs/acceptance/perf/perf_results.json.
# Запуск (не в pytest): sudo docker compose run --rm e2e \
#     bash -lc "cd /e2e && python audit/perf_check.py"

import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/e2e")

from playwright.sync_api import sync_playwright  # noqa: E402

from conftest import BASE_URL, SMOKE_TEXT, wait_analysis  # noqa: E402

OUT_DIR = Path("/e2e/screenshots/perf")
RUNS = 3
BUDGET_BROWSER_S = 5.0
BUDGET_SOLVE_S = 10.0
BUDGET_HEALTHZ_P95_MS = 50.0
COLD_TASKS = ["TASK-LSS-04", "TASK-LSS-05", "TASK-LSS-10"]

HEALTHZ_JS = """
async ({task_id, data}) => {
    const t0 = performance.now();
    let stop = false;
    const sampled = [];
    const sampler = (async () => {
        while (!stop) {
            const s = performance.now();
            await fetch('/healthz');
            sampled.push(performance.now() - s);
            await new Promise((res) => setTimeout(res, 20));
        }
        return sampled;
    })();
    const sr = await fetch('/solve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_id: task_id, data: data}),
    });
    const solve_ms = performance.now() - t0;
    stop = true;
    const all = await sampler;
    return {
        solve_ms: solve_ms,
        solve_ok: sr.ok,
        first5_ms: all.slice(0, 5),
        sampled_ms: all,
    };
}
"""


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[idx]


def median(values: list[float]) -> float:
    return sorted(values)[len(values) // 2]


def http(method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.status, resp.read()


def catalog_prefill() -> dict[str, dict]:
    _, raw = http("GET", "/catalog")
    return {t["task_id"]: (t.get("prefill") or {}) for t in json.loads(raw)}


def browser_full_scenario(browser) -> float:
    """(a) goto → parse → анализ → граф отрендерен, с загрузкой страницы, с."""
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    try:
        t0 = time.perf_counter()
        page.goto(BASE_URL)
        page.wait_for_selector("#input-text")
        page.fill("#input-text", SMOKE_TEXT)
        page.click("#btn-run-text")
        wait_analysis(page)
        return time.perf_counter() - t0
    finally:
        page.close()


def solve_api_ms(task_id: str, data: dict) -> float:
    """(b) POST /solve через urllib, мс."""
    body = json.dumps({"task_id": task_id, "data": data}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/solve",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        resp.read()
    return (time.perf_counter() - t0) * 1000


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prefills = catalog_prefill()
    results: dict = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "runs": RUNS,
        "statistic": "median",
        "budgets": {
            "browser_full_scenario_s": BUDGET_BROWSER_S,
            "solve_lss10_api_s": BUDGET_SOLVE_S,
            "healthz_p95_ms": BUDGET_HEALTHZ_P95_MS,
        },
    }

    healthz_runs: list[dict] = []
    scenario_samples: list[float] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # (c) — холодный solve (уникальный ключ кэша), из браузера
        for task_id in COLD_TASKS:
            data = dict(prefills.get(task_id) or {})
            data["audit_fresh"] = int(time.time() * 1_000_000)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.goto(BASE_URL)
            page.wait_for_selector(".theme-select")
            d = page.evaluate(HEALTHZ_JS, {"task_id": task_id, "data": data})
            page.close()
            samples = d["sampled_ms"]
            healthz_runs.append(
                {
                    "task_id": task_id,
                    "solve_ms": round(d["solve_ms"], 1),
                    "solve_ok": d["solve_ok"],
                    "n_samples": len(samples),
                    "first5_ms": [round(s, 2) for s in d["first5_ms"]],
                    "max_ms": round(max(samples), 2),
                    "p95_ms": round(p95(samples), 2),
                }
            )
            print(
                f"(c) {task_id}: solve {d['solve_ms']:.0f} мс, "
                f"healthz n={len(samples)} p95 {p95(samples):.1f} мс "
                f"max {max(samples):.1f} мс"
            )
        # (a) — 3 полных сценария, свежие страницы
        for i in range(RUNS):
            sample = browser_full_scenario(browser)
            scenario_samples.append(sample)
            print(f"(a) run {i + 1}: {sample:.2f} с")
        browser.close()

    # (b) — 3 замера LSS-10 (data={} — попадает в LRU после первого) + 1 холодный
    solve_samples = [solve_api_ms("TASK-LSS-10", {}) for _ in range(RUNS)]
    cold_data = dict(prefills.get("TASK-LSS-10") or {})
    cold_data["audit_fresh"] = int(time.time() * 1_000_000)
    solve_cold_ms = solve_api_ms("TASK-LSS-10", cold_data)
    for i, s in enumerate(solve_samples, start=1):
        print(f"(b) run {i}: {s:.0f} мс")
    print(f"(b) cold: {solve_cold_ms:.0f} мс")

    scenario_median = median(scenario_samples)
    solve_median = median(solve_samples)
    healthz_p95_median = median([r["p95_ms"] for r in healthz_runs])

    results["browser_full_scenario_s"] = {
        "samples": [round(s, 3) for s in scenario_samples],
        "median": round(scenario_median, 3),
        "budget_s": BUDGET_BROWSER_S,
        "pass": scenario_median <= BUDGET_BROWSER_S,
    }
    results["solve_lss10_api_ms"] = {
        "samples": [round(s, 1) for s in solve_samples],
        "median": round(solve_median, 1),
        "cold": round(solve_cold_ms, 1),
        "note": "3 замера с data={} (первый — cold при чистом кэше, остальные warm); "
        "cold — отдельный замер с уникальным ключом кэша",
        "budget_s": BUDGET_SOLVE_S,
        "pass": max(solve_median, solve_cold_ms) / 1000 <= BUDGET_SOLVE_S,
    }
    results["healthz_during_solve"] = {
        "method": "browser fetch /healthz: первые 5 сразу после POST /solve, "
        "далее ~каждые 20 мс до конца solve (метод audit_extra2); solve холодный "
        "(уникальный ключ кэша в data)",
        "runs": healthz_runs,
        "median_p95_ms": round(healthz_p95_median, 2),
        "max_overall_ms": round(max(r["max_ms"] for r in healthz_runs), 2),
        "budget_ms": BUDGET_HEALTHZ_P95_MS,
        "pass": all(r["p95_ms"] < BUDGET_HEALTHZ_P95_MS for r in healthz_runs)
        and all(r["solve_ok"] for r in healthz_runs),
    }

    ok = (
        results["browser_full_scenario_s"]["pass"]
        and results["solve_lss10_api_ms"]["pass"]
        and results["healthz_during_solve"]["pass"]
    )
    results["pass"] = ok
    out_path = OUT_DIR / "perf_results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"perf results: {out_path}; pass={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
