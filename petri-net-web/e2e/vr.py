# Visual regression (E2E-12, фаза 2.6): пиксельный диф через Pillow.
# Базлайны — docs/acceptance/vr-baseline/ (генерация: audit/vr_baseline.py).
# Критерий: размер страницы совпадает и < 1% пикселей отличаются > 30 по
# яркости (L). Исключения (маскируются в baseline и current):
#   - #canvas-net — layout COSE стартует из случайных позиций (cytoscore),
#     узлы/рёбра дрифтуют между прогонками (~0.7% пикселей);
#   - #session-badge — /parse не возвращает name (ответ без поля), бейдж
#     показывает uuid сессии.
# Исключённые элементы проверяются отдельно: существование + совпадение рамки.

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from conftest import BASE_URL, wait_analysis

BASELINES_DIR = Path("/e2e/screenshots/vr-baseline")
CURRENT_DIR = Path("/e2e/screenshots/vr-current")

MAX_DIFF_PIXEL_RATIO = 0.01
PIXEL_LUMA_THRESHOLD = 30
MASKED_SELECTORS = ("#canvas-net", "#session-badge")
SETTLE_MS = 500


@dataclass
class MaskBox:
    selector: str
    x: int
    y: int
    w: int
    h: int


@dataclass
class VrResult:
    baseline: Path
    current: Path
    size: tuple[int, int]
    diff_pixels: int
    diff_ratio: float
    masks: list[MaskBox] = field(default_factory=list)


def set_theme(page, theme: str) -> None:
    """Тема задаётся ДО сценария: localStorage + reload (анти-FOUC из index.html)."""
    page.goto(BASE_URL)
    page.wait_for_selector(".theme-select")
    page.evaluate("(t) => localStorage.setItem('pn-theme', t)", theme)
    page.reload()
    page.wait_for_selector(".theme-select")
    actual = page.evaluate("() => document.documentElement.dataset.theme")
    assert actual == theme, f"ожидалась тема {theme}, получена {actual}"


def settle(page) -> None:
    """Дождаться одноразовых таймеров канвасов и шрифтов.

    NetCanvas: fit @150 мс после mount; оба канваса: resize-debounce @200 мс
    (FR-613); шрифты KaTeX грузятся асинхронно. Без дождидки возможен доп.
    шум вне маскируемых областей.
    """
    page.wait_for_timeout(SETTLE_MS)
    page.evaluate("() => document.fonts.ready")


def render_main(page) -> None:
    """Главный экран «Сеть Петри» после полного анализа эталонной сети."""
    page.goto(BASE_URL)
    page.wait_for_selector("#input-text")
    page.click("#btn-run-text")
    wait_analysis(page)
    settle(page)


def render_report_lss14(page) -> None:
    """Экран «Задание из практикума»: отчёт TASK-LSS-14 (KaTeX-формулы)."""
    page.goto(BASE_URL)
    page.wait_for_selector(".theme-select")
    page.click("button:has-text('Задание из практикума')")
    page.wait_for_selector(".task-card")
    page.click("button.tab:has-text('ЛСС')")
    page.locator(".task-card", has_text="TASK-LSS-14").first.locator(
        "button", has_text="Решить"
    ).click()
    page.wait_for_selector("#task-data")
    page.locator(".solver button.primary", has_text="Решить").click()
    page.wait_for_selector(".report .katex")
    settle(page)


def capture(page) -> tuple[Image.Image, list[MaskBox]]:
    """Скриншот full page + рамки маскируемых элементов (от верхней точки).

    Элемент может отсутствовать (badge — только после создания сессии),
    поэтому рамки снимаются JS-проверкой без ожидания.
    """
    page.evaluate("() => window.scrollTo(0, 0)")
    boxes = page.evaluate(
        """(selectors) => {
            const out = {};
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (!el) continue;
                const r = el.getBoundingClientRect();
                out[sel] = {x: r.x, y: r.y + window.scrollY, w: r.width, h: r.height};
            }
            return out;
        }""",
        list(MASKED_SELECTORS),
    )
    masks = [
        MaskBox(sel, int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"]))
        for sel, b in boxes.items()
    ]
    png = page.screenshot(full_page=True)
    return Image.open(io.BytesIO(png)).convert("RGB"), masks


def _mask(image: Image.Image, masks: list[MaskBox]) -> Image.Image:
    if not masks:
        return image
    masked = image.copy()
    draw = ImageDraw.Draw(masked)
    for m in masks:
        x1, y1 = m.x + m.w - 1, m.y + m.h - 1
        draw.rectangle([m.x, m.y, max(x1, m.x), max(y1, m.y)], fill=(0, 0, 0))
    return masked


def compare(baseline: Path, current: Path, masks: list[MaskBox]) -> VrResult:
    """Пиксельный диф baseline↔current с масками (маска применяется к обоим)."""
    if not baseline.exists():
        raise AssertionError(
            f"бэйджи нет: {baseline} — сгенерировать: "
            "python audit/vr_baseline.py (docs/TEST_PLAN.md §5 E2E-12)"
        )
    a = _mask(Image.open(baseline).convert("RGB"), masks)
    b = _mask(Image.open(current).convert("RGB"), masks)
    if a.size != b.size:
        raise AssertionError(
            f"размер страницы: baseline {a.size} != current {b.size}"
        )
    diff = ImageChops.difference(a, b).convert("L")
    hist = diff.histogram()
    bad = sum(hist[PIXEL_LUMA_THRESHOLD + 1 :])
    total = a.size[0] * a.size[1]
    return VrResult(baseline, current, a.size, bad, bad / total, masks)


def assert_within_budget(result: VrResult, name: str) -> None:
    if result.diff_ratio > MAX_DIFF_PIXEL_RATIO:
        raise AssertionError(
            f"visual regression {name}: {result.diff_pixels} пикселей "
            f"({result.diff_ratio:.4%}) отличаются > {PIXEL_LUMA_THRESHOLD} "
            f"по яркости при пороге {MAX_DIFF_PIXEL_RATIO:.1%}; "
            f"baseline={result.baseline.name}, current={result.current.name}, "
            f"маски={[m.selector for m in result.masks]}"
        )
