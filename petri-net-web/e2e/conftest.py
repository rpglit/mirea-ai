# E2E conftest: playwright fixtures, smoke constants, failure screenshots.

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
SCREENSHOTS_DIR = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots"))

SMOKE_TEXT: str = """S = (P, T, I, O, µ),
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
µ = (7, 4, 2, 5, 4, 3)."""

SMOKE_JSON: str = json.dumps(
    {
        "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
        "transitions": ["t1", "t2", "t3", "t4", "t5"],
        "inputs": {
            "t1": {"p1": 2},
            "t2": {"p1": 1, "p6": 1},
            "t3": {"p2": 1},
            "t4": {"p2": 1, "p3": 1, "p4": 2},
            "t5": {"p5": 2},
        },
        "outputs": {
            "t1": {"p2": 1},
            "t2": {"p3": 2},
            "t3": {"p4": 3},
            "t4": {"p5": 1, "p6": 1},
            "t5": {"p1": 1, "p3": 1},
        },
        "initial_marking": {"p1": 7, "p2": 4, "p3": 2, "p4": 5, "p5": 4, "p6": 3},
    },
    sort_keys=True,
)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        yield p.chromium.launch(headless=True)


@pytest.fixture
def page(browser):
    new_page = browser.new_page(viewport={"width": 1400, "height": 900})
    console_problems: list[str] = []
    new_page.on(
        "console",
        lambda msg: console_problems.append(f"{msg.type}: {msg.text}")
        if msg.type in ("error", "warning")
        else None,
    )
    new_page.on("pageerror", lambda exc: console_problems.append(f"pageerror: {exc}"))
    yield new_page
    new_page.close()
    # NFR-107: console «чистый» — 0 JS-ошибок и 0 warning во всех сценариях
    if console_problems:
        raise AssertionError(
            "console не чистый (NFR-107):\n" + "\n".join(console_problems[:20])
        )


def analyze_via_text(page: Page) -> None:
    page.goto(BASE_URL)
    page.wait_for_selector("#input-text")
    page.click("#btn-run-text")
    wait_analysis(page)


def wait_analysis(page: Page, node_count: int = 1503, timeout_ms: int = 120000) -> None:
    """Wait until the full pipeline finished: stats + rendered canvas + step panel.

    The #graph-stats text appears before Cytoscape finishes rendering the
    canvas, so require all three markers (graph canvas node count, stats text,
    non-empty step panel) before returning.
    """
    page.wait_for_function(
        "(count) => {"
        " const s = document.getElementById('graph-stats');"
        " const g = window.Registry && window.Registry.graph;"
        " const active = document.querySelectorAll('#active-list .btn-transition').length;"
        " return !!s && s.textContent.includes('узлов: ' + count)"
        " && !!g && g.$('node').length === count && active >= 1;"
        "}",
        arg=node_count,
        timeout=timeout_ms,
    )


def wait_net_label(page: Page, label: str, timeout_ms: int = 15000) -> None:
    """Wait until the net canvas shows a place label like ``"p1 (5)"``."""
    page.wait_for_function(
        "(label) => {"
        " const g = window.Registry && window.Registry.net;"
        " return !!g && g.$('node').some((n) => n.data('label') === label);"
        "}",
        arg=label,
        timeout=timeout_ms,
    )


def graph_node_count(page: Page) -> int:
    return page.evaluate(
        "() => (window.Registry && window.Registry.graph) ? window.Registry.graph.$('node').length : 0"
    )


def net_labels(page: Page) -> list:
    return page.evaluate(
        "() => (window.Registry && window.Registry.net) ? window.Registry.net.$('node').map((n) => n.data('label')) : []"
    )


def props_text(page: Page) -> str:
    return page.inner_text("#props")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page is not None:
            failures = SCREENSHOTS_DIR / "failures"
            failures.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(failures / f"{item.name}.png"), full_page=True)
            except Exception:
                pass
