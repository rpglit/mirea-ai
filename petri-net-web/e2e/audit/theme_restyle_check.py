# Проверка фазы 2.2 (chunk 2): переключение темы через UI рестилит Cytoscape
# на живом инстансе (без destroy/re-layout) и не сбрасывает позиции/zoom.

import sys

sys.path.insert(0, "/e2e")

from playwright.sync_api import sync_playwright  # noqa: E402

from conftest import BASE_URL, analyze_via_text  # noqa: E402

EVAL_STYLE = """
() => {
  const getProp = (cy, selector, name) => {
    const s = cy.style();
    for (let i = 0; i < s.length; i++) {
      const e = s[i];
      if (e.selector && e.selector.inputText === selector) {
        const p = (e.properties || []).find((x) => x.name === name);
        return p ? p.strValue : null;
      }
    }
    return null;
  };
  return {
    net: getProp(window.Registry.net, 'node', 'background-color'),
    graph: getProp(window.Registry.graph, 'node', 'background-color'),
  };
}
"""
EVAL_POSE = """
() => {
  const n = window.Registry.net.$('node').first();
  return [n.position().x, n.position().y, window.Registry.net.zoom()];
}
"""


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

        analyze_via_text(page)
        assert page.evaluate(
            "() => !!window.Registry.net && !!window.Registry.graph"
        ), "canvases не отрисованы"
        page.evaluate(
            "() => { window.__ref_net = window.Registry.net; window.__ref_graph = window.Registry.graph; }"
        )
        before = page.evaluate(EVAL_STYLE)
        pose_before = page.evaluate(EVAL_POSE)

        page.select_option(".theme-select", "dark")
        assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
        assert page.evaluate("() => window.Registry.net === window.__ref_net"), "инстанс net заменён"
        assert page.evaluate("() => window.Registry.graph === window.__ref_graph"), "инстанс graph заменён"
        after = page.evaluate(EVAL_STYLE)
        pose_after = page.evaluate(EVAL_POSE)

        print(f"net bg:    {before['net']} -> {after['net']}")
        print(f"graph bg:  {before['graph']} -> {after['graph']}")
        print(f"pose before: {pose_before}")
        print(f"pose after:  {pose_after}")
        light = {"net": "rgb(255,255,255)", "graph": "rgb(232,237,251)"}
        dark = {"net": "rgb(42,42,42)", "graph": "rgb(43,53,70)"}
        assert before == light, before
        assert after == dark, after
        assert pose_before == pose_after, (pose_before, pose_after)

        page.select_option(".theme-select", "light")
        assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
        assert page.evaluate(EVAL_STYLE) == light

        browser.close()

    print("console problems:", problems if problems else "none")
    if problems:
        sys.exit(1)
    print("THEME RESTYLE CHECK OK")


if __name__ == "__main__":
    main()
