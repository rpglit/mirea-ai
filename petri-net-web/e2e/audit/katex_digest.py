# Standalone audit: KaTeX render digest of every unique formula string from
# /solve LSS-01..23 (finding review #6, MATH_RENDER_PLAN section 1).
#
# Run: sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/katex_digest.py"

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
OUT_DIR = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots")) / "math"
HERE = Path(__file__).resolve().parent
RENDER_JS = HERE / "katex_render.js"

FORMULA_CHARS = set("0123456789+-*/=^().,")


def fetch_report(task_id: str) -> dict:
    body = json.dumps({"task_id": task_id, "data": {}}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/solve",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def is_formula_string(value: str) -> bool:
    if not value or any(ord(c) > 127 for c in value):
        return False
    return any(c in FORMULA_CHARS for c in value)


def collect_strings(node, acc: set) -> None:
    if isinstance(node, str):
        if is_formula_string(node):
            acc.add(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            if str(k).endswith("_tex"):
                continue
            collect_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            collect_strings(v, acc)


def main() -> int:
    strings: set = set()
    for i in range(1, 24):
        report = fetch_report(f"TASK-LSS-{i:02d}")
        collect_strings(report["answer"], strings)
        for step in report["solution"]:
            if step.get("data") is not None:
                collect_strings(step["data"], strings)
    ordered = sorted(strings)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    strings_path = OUT_DIR / "katex_digest_strings.json"
    strings_path.write_text(json.dumps(ordered, ensure_ascii=False), encoding="utf-8")
    out_path = OUT_DIR / "katex_render_digest.json"
    subprocess.run(["node", str(RENDER_JS), str(strings_path), str(out_path)], check=False)
    if not out_path.exists():
        print("katex digest: node renderer failed", file=sys.stderr)
        return 1
    digest = json.loads(out_path.read_text(encoding="utf-8"))
    digest["generated"] = datetime.now(timezone.utc).isoformat()
    digest["source"] = f"POST {BASE_URL}/solve TASK-LSS-01..23"
    digest["selection"] = (
        "unique ASCII-only strings from answer + solution[].data (recursive, "
        "keys *_tex excluded) containing at least one of: 0-9 + - * / = ^ ( ) . ,"
    )
    digest["katex_version"] = "0.19.0"
    digest["unique_strings"] = len(ordered)
    out_path.write_text(json.dumps(digest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"katex digest: unique_strings={len(ordered)} total={digest['total']} "
        f"ok={digest['ok']} failed={len(digest['failed'])} warnings={digest.get('warnings', 0)}"
    )
    for item in digest["failed"][:10]:
        print(f"  FAIL [{item['mode']}] {item['tex'][:80]} :: {item['error'][:120]}", file=sys.stderr)
    return 0 if not digest["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
