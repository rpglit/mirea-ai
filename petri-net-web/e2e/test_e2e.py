# E2E scenarios E2E-1..E2E-5 (docs/TEST_PLAN.md section 5).

import json
from pathlib import Path

from playwright.sync_api import Page

from conftest import (
    BASE_URL,
    SMOKE_JSON,
    SCREENSHOTS_DIR,
    analyze_via_text,
    graph_node_count,
    net_labels,
    props_text,
    wait_analysis,
    wait_net_label,
)


def test_e2e1_text_intake_full_analysis(page: Page) -> None:
    """E2E-1: text intake + full analysis (acceptance screenshot)."""
    analyze_via_text(page)
    assert graph_node_count(page) == 1503
    net_nodes = page.evaluate(
        "() => (window.Registry && window.Registry.net) ? window.Registry.net.$('node').length : 0"
    )
    assert net_nodes == 11
    props = props_text(page)
    assert "29" in props
    assert "L1" in props
    assert "23" in props
    assert "нет" in props
    page.screenshot(path=str(SCREENSHOTS_DIR / "e2e-1-analysis.png"), full_page=True)


def test_e2e2_stepping(page: Page) -> None:
    """E2E-2: one-click firing, undo, reset, clickable history (BUG-5/6)."""
    analyze_via_text(page)
    assert page.locator("#active-list .btn-transition").count() == 5
    # one click on the transition fires it (FR-401, BUG-5)
    page.locator("#active-list .btn-transition", has_text="t1").click()
    wait_net_label(page, "p1 (5)")
    labels = net_labels(page)
    assert "p1 (5)" in labels
    assert "p2 (5)" in labels
    page.click("#btn-undo")
    wait_net_label(page, "p1 (7)")
    labels = net_labels(page)
    assert "p1 (7)" in labels
    assert "p2 (4)" in labels
    # the "Срабатывание" button fires the first enabled transition
    page.click("#btn-step")
    wait_net_label(page, "p1 (5)")
    # clicking the first history line restores that state (BUG-6)
    page.locator("#history-list .history-line").first.click()
    wait_net_label(page, "p1 (5)")
    page.click("#btn-reset")
    page.wait_for_function(
        "() => document.querySelectorAll('#history-list .history-line').length === 0",
        timeout=15000,
    )
    labels = net_labels(page)
    assert "p1 (7)" in labels


def test_e2e3_exports(page: Page) -> None:
    """E2E-3: exports (CSV + JSON report)."""
    analyze_via_text(page)
    with page.expect_download() as csv_info:
        page.click("#btn-export-csv")
    csv_path = csv_info.value.path()
    text = Path(csv_path).read_text(encoding="utf-8")
    lines = text.strip().split("\n")
    assert lines[0] == "p1,p2,p3,p4,p5,p6"
    assert len(lines) == 1504
    assert lines[1] == "7,4,2,5,4,3"
    assert "omega" not in text
    with page.expect_download() as json_info:
        page.click("#btn-export-json")
    report = json.loads(Path(json_info.value.path()).read_text(encoding="utf-8"))
    assert report["global_k"] == 29
    assert report["liveness"]["level"] == "L1"
    assert len(report["deadlocks"]) == 23


def test_e2e4_json_intake(page: Page) -> None:
    """E2E-4: JSON intake."""
    page.goto(BASE_URL)
    page.wait_for_selector("#tab-json")
    page.click("#tab-json")
    page.fill("#input-json", SMOKE_JSON)
    page.click("#btn-run-json")
    wait_analysis(page)
    assert graph_node_count(page) == 1503
    props = props_text(page)
    assert "29" in props
    assert "L1" in props
    assert "23" in props


def test_e2e5_session_history(page: Page) -> None:
    """E2E-5: session history restore."""
    analyze_via_text(page)
    page.click("#btn-sessions")
    items = page.locator("#sessions-list .session-item")
    assert items.count() >= 1
    items.first.click()
    wait_analysis(page, timeout_ms=60000)
    assert graph_node_count(page) == 1503
    props = props_text(page)
    assert "29" in props


def test_e2e6_task_picker_solve_pn(page: Page) -> None:
    """E2E-6: «Задание из практикума» — каталог, prefill, solve, отчёт (FR-331..333)."""
    page.goto(BASE_URL)
    page.click("button:has-text('Задание из практикума')")
    page.wait_for_selector(".task-card")
    assert page.locator(".task-card").count() == 71
    page.click("button.tab:has-text('Сети Петри')")
    page.wait_for_selector(".task-card")
    assert page.locator(".task-card").count() == 40
    card = page.locator(".task-card", has_text="TASK-PN-05").first
    card.locator("button", has_text="Решить").click()
    page.wait_for_selector("#task-data")
    data = page.input_value("#task-data")
    assert "initial_marking" in data
    page.locator(".solver button.primary", has_text="Решить").click()
    page.wait_for_selector(".report")
    report_text = page.inner_text(".report")
    assert "Дано" in report_text
    assert "Найти" in report_text
    assert "Решение" in report_text
    assert "Ответ" in report_text
    assert "(5,3,4,6,3,3)" in report_text
    page.screenshot(path=str(SCREENSHOTS_DIR / "e2e-6-solve-pn.png"), full_page=True)


def test_e2e7_fa_solve_automaton_graph(page: Page) -> None:
    """E2E-7: FA-03 — граф автомата, прохождение слова по тактам (FR-501)."""
    page.goto(BASE_URL)
    page.click("button:has-text('Задание из практикума')")
    page.wait_for_selector(".task-card")
    page.locator(".task-card", has_text="TASK-FA-03").first.locator(
        "button", has_text="Решить"
    ).click()
    page.wait_for_selector("#task-data")
    page.locator(".solver button.primary", has_text="Решить").click()
    page.wait_for_selector(".report .canvas")
    assert (
        page.evaluate("() => (window.Registry.automaton ? window.Registry.automaton.$('node').length : 0)")
        == 4
    )
    report_text = page.inner_text(".report")
    assert "w0" in report_text and "s3" in report_text
    # по тактам: слово p1 p2 p2 p1 p2 -> s0 s0 s1 s3 s3 s0
    page.click("button:has-text('Показать прохождение')")
    assert (
        page.evaluate("() => (window.Registry.automaton ? window.Registry.automaton.$('node.path-current').length : 0)")
        == 1
    )
    page.click("button:has-text('Следующий такт')")
    page.click("button:has-text('Показать весь путь')")
    assert (
        page.evaluate("() => (window.Registry.automaton ? window.Registry.automaton.$('node.path-state').length : 0)")
        == 3
    )
    page.screenshot(path=str(SCREENSHOTS_DIR / "e2e-7-fa-graph.png"), full_page=True)


def test_e2e8_png_exports(page: Page) -> None:
    """E2E-8: PNG-экспорт сети и графа (BUG-1, FR-405/FR-503)."""
    analyze_via_text(page)
    page.click("#canvas-net")
    with page.expect_download() as png_info:
        page.click("#btn-export-png")
    blob = Path(png_info.value.path()).read_bytes()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(blob) > 1000
    page.click("#canvas-graph")
    with page.expect_download() as png_info2:
        page.click("#btn-export-png")
    blob2 = Path(png_info2.value.path()).read_bytes()
    assert blob2[:8] == b"\x89PNG\r\n\x1a\n"
    with page.expect_download() as all_info:
        page.click("#btn-export-all-png")
    blob3 = Path(all_info.value.path()).read_bytes()
    assert blob3[:8] == b"\x89PNG\r\n\x1a\n"
