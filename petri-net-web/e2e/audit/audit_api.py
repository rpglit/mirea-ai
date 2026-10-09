#!/usr/bin/env python3
"""Standalone API / performance / caching audit (NOT a pytest test).

Run (containers only):

    sudo docker compose run --rm e2e bash -lc "cd /e2e && python audit/audit_api.py"

Hits the already-running app (BASE_URL, default http://app:8000). Read-only
towards product code; creates a couple of throwaway sessions for the
restore-bug check (they stay in the session store — harmless test data).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://app:8000")
OUT = Path(os.environ.get("SCREENSHOT_DIR", "/e2e/screenshots")) / "audit"
OUT.mkdir(parents=True, exist_ok=True)


def req(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            dt = (time.perf_counter() - t0) * 1000
            return {
                "status": resp.status,
                "ms": round(dt, 1),
                "headers": {k.lower(): v for k, v in resp.headers.items()},
                "body": raw,
            }
    except urllib.error.HTTPError as e:
        raw = e.read()
        dt = (time.perf_counter() - t0) * 1000
        return {
            "status": e.code,
            "ms": round(dt, 1),
            "headers": {k.lower(): v for k, v in e.headers.items()},
            "body": raw,
        }


def jbody(r: dict):
    try:
        return json.loads(r["body"])
    except Exception:
        return None


def main() -> None:
    out: dict = {"base_url": BASE_URL, "sections": {}}

    # ---------------- 1. Static asset HTTP caching ---------------------------
    root = req("GET", "/")
    html = root["body"].decode("utf-8", "replace")
    assets = sorted({line.strip().split('"')[-2] for line in html.splitlines() if "/assets/" in line})
    asset_headers = {}
    for a in assets[:6]:
        r = req("GET", a)
        h = r["headers"]
        asset_headers[a] = {
            "status": r["status"],
            "cache_control": h.get("cache-control"),
            "etag": h.get("etag"),
            "last_modified": h.get("last-modified"),
            "content_length": h.get("content-length"),
        }
    out["sections"]["static_cache"] = {
        "root_headers": {
            "cache_control": root["headers"].get("cache-control"),
            "etag": root["headers"].get("etag"),
            "last_modified": root["headers"].get("last-modified"),
            "content_type": root["headers"].get("content-type"),
        },
        "assets_checked": asset_headers,
    }

    # ---------------- 2. Smoke pipeline timing over HTTP ---------------------
    smoke_text = (
        "S = (P, T, I, O, µ),\n"
        "P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},\n"
        "I(t1) = {p1, p1}, O(t1) = {p2},\n"
        "I(t2) = {p1, p6}, O(t2) = {p3, p3},\n"
        "I(t3) = {p2},       O(t3) = {p4, p4, p4},\n"
        "I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},\n"
        "I(t5) = {p5, p5},   O(t5) = {p1, p3},\n"
        "µ = (7, 4, 2, 5, 4, 3)."
    )
    parse = req("POST", "/parse", {"format": "text", "payload": smoke_text, "name": "audit-smoke"})
    sid = jbody(parse)["session_id"]
    graph = req("POST", "/graph", {"session_id": sid, "mode": "auto"})
    props = req("POST", "/properties", {"session_id": sid})
    state = req("GET", f"/state/{sid}")
    out["sections"]["smoke_pipeline_ms"] = {
        "parse": parse["ms"],
        "graph": graph["ms"],
        "properties": props["ms"],
        "state": state["ms"],
        "total": round(parse["ms"] + graph["ms"] + props["ms"] + state["ms"], 1),
        "graph_nodes": jbody(graph)["node_count"],
        "graph_edges": jbody(graph)["edge_count"],
        "props_global_k": jbody(props)["global_k"],
    }

    # ---------------- 3. Session restore: v2 fields lost? --------------------
    inh_form = {
        "places": ["p1", "p2"],
        "transitions": ["t1"],
        "arcs": [
            {"source": "p2", "target": "t1", "weight": 1, "direction": "input"},
            {"source": "t1", "target": "p1", "weight": 1, "direction": "output"},
            {"source": "p1", "target": "t1", "direction": "inhibitor"},
        ],
        "initial_marking": {"p1": 0, "p2": 1},
    }
    p2 = req("POST", "/parse", {"format": "form", "payload": inh_form, "name": "audit-inh"})
    sid2 = jbody(p2)["session_id"]
    parse_fields = sorted(k for k in jbody(p2) if k not in ("session_id",))
    sess = req("GET", f"/sessions/{sid2}")
    sess_fields = sorted(k for k in jbody(sess) if k not in ("session_id",))
    req("DELETE", f"/sessions/{sid2}")
    out["sections"]["session_restore_fields"] = {
        "parse_response_fields": parse_fields,
        "get_session_fields": sess_fields,
        "lost_on_restore": sorted(set(parse_fields) - set(sess_fields)),
    }

    # delays net: parse ok, /graph must be 422 unsupported_model (delays)
    dl_form = {
        "places": ["p1"],
        "transitions": ["t1"],
        "arcs": [
            {"source": "p1", "target": "t1", "weight": 1, "direction": "input"},
            {"source": "t1", "target": "p1", "weight": 1, "direction": "output"},
        ],
        "initial_marking": {"p1": 1},
        "delays": {"t1": {"p1": 4}},
    }
    p3 = req("POST", "/parse", {"format": "form", "payload": dl_form, "name": "audit-dl"})
    sid3 = jbody(p3)["session_id"]
    g3 = req("POST", "/graph", {"session_id": sid3, "mode": "auto"})
    req("DELETE", f"/sessions/{sid3}")
    out["sections"]["delays_graph"] = {"status": g3["status"], "body": jbody(g3)}

    # unbounded counter: /graph auto -> 413 cap_exceeded, coverability ok
    counter = {
        "places": ["p1"],
        "transitions": ["t1"],
        "inputs": {"t1": {}},
        "outputs": {"t1": {"p1": 1}},
        "initial_marking": {"p1": 1},
    }
    p4 = req("POST", "/parse", {"format": "json", "payload": counter, "name": "audit-counter"})
    sid4 = jbody(p4)["session_id"]
    g4 = req("POST", "/graph", {"session_id": sid4, "mode": "auto"})
    g4c = req("POST", "/graph", {"session_id": sid4, "mode": "coverability"})
    req("DELETE", f"/sessions/{sid4}")
    out["sections"]["cap_and_coverability"] = {
        "auto_status": g4["status"],
        "auto_body": jbody(g4),
        "coverability_status": g4c["status"],
        "coverability_nodes": jbody(g4c).get("node_count") if g4c["status"] == 200 else None,
    }

    # ---------------- 4. /solve: all catalog tasks, timings ------------------
    cat = jbody(req("GET", "/catalog"))
    timings = []
    for t in cat:
        data = t.get("prefill") or {}
        r = req("POST", "/solve", {"task_id": t["task_id"], "data": data}, timeout=90)
        ok = r["status"] == 200
        timings.append(
            {
                "task_id": t["task_id"],
                "group": t["group"],
                "ms": r["ms"],
                "status": r["status"],
                "ok": ok,
                "error": None if ok else (jbody(r) or {}).get("error", {}).get("message"),
            }
        )
    timings.sort(key=lambda x: -x["ms"])
    out["sections"]["solve_all"] = {
        "count": len(cat),
        "total_ms": round(sum(x["ms"] for x in timings), 1),
        "failed": [x for x in timings if not x["ok"]],
        "top10_heaviest": timings[:10],
    }

    # ---------------- 5. Event-loop blocking during /solve -------------------
    # Heaviest task from step 4 (or TASK-PN-05): start it in a thread and probe
    # /healthz latency while it runs.
    heavy = timings[0]["task_id"] if timings else "TASK-PN-05"
    heavy_task = next(t for t in cat if t["task_id"] == heavy)
    probe: dict = {}

    def heavy_solve():
        r = req("POST", "/solve", {"task_id": heavy, "data": heavy_task.get("prefill") or {}}, timeout=120)
        probe["solve_ms"] = r["ms"]
        probe["solve_status"] = r["status"]

    th = threading.Thread(target=heavy_solve)
    th.start()
    time.sleep(0.15)
    probes = []
    for _ in range(6):
        t0 = time.perf_counter()
        try:
            urllib.request.urlopen(BASE_URL + "/healthz", timeout=5)
            probes.append(round((time.perf_counter() - t0) * 1000, 1))
        except Exception as e:  # noqa: BLE001
            probes.append(f"err:{type(e).__name__}")
        time.sleep(0.1)
    th.join()
    out["sections"]["event_loop_block"] = {
        "heavy_task": heavy,
        "healthz_probes_ms": probes,
        "solve": probe,
    }

    # ---------------- 6. GET /sessions list cost -----------------------------
    ls = req("GET", "/sessions?limit=50")
    n = len(jbody(ls) or [])
    out["sections"]["sessions_list"] = {"ms": ls["ms"], "count": n, "limit": 50}

    digest_path = OUT / "audit_api.json"
    digest_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n[audit_api] digest -> {digest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
