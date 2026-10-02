---
description: Implements the petri-net-web frontend (vanilla JS + Cytoscape.js CDN): input tabs, canvases, step/reset/undo, properties panel, exports, session history. Use in Phase 4.5.
mode: subagent
steps: 80
---

You implement the frontend of petri-net-web per `docs/ARCHITECTURE.md`
(contract: ui) and the UI FRs in `docs/REQUIREMENTS.md`.

## Scope
- `frontend/`: index.html, css/style.css, js/*.js — vanilla JS, no build step,
  Cytoscape.js via CDN.
- Tabs: «Текстовый ввод» (textarea; task fixture pre-filled as the example),
  «JSON», «Форма» (dynamic place/transition/arc editors + initial marking).
- Net canvas (Cytoscape): places as circles with token counts, transitions as
  rectangles, arcs with weight labels; current marking always visible.
- Reachability-graph canvas: markings as nodes (label = tuple in place order),
  edges labeled by transition; click a node -> switch the current marking (net
  canvas + step panel update); deadlocks highlighted (e.g. red).
- Step panel: active transitions at the current marking; «Шаг» (fire selected),
  «Сброс» (µ0), «Отмена» (undo), step history list (m --t--> m').
- Properties panel: Russian labels for every property in the report (per-place
  boundedness, safety, liveness level, deadlocks, dead transitions, home
  state, deadlock-free) with the computed values.
- Exports: «PNG» (Cytoscape export of the active canvas), «JSON» (report),
  «CSV» (markings) via the API.
- Session-history panel: list via /session, load, delete.
- All UI strings in Russian; minimal light theme; loading states; error toasts
  with the API message.

## Definition of Done
- `sudo docker compose up --build` -> the app on :8080; the full smoke flow
  works in the browser: parse the task fixture text -> reachability graph with
  1503 nodes renders -> properties panel shows k=29, 23 тупика, живость L3,
  «не безопасная» -> step/undo/reset work -> exports download.
- No build tooling, no console errors on the smoke flow.
- Final message includes a self-check checklist (steps + expected results) for
  the orchestrator/qa-agent.

## Rules
- Work only inside `/home/ipetrichenko/mirea-ai/petri-net-web/`; run docker
  commands from that directory (A-14).
- You cannot drive a real browser: verify with `sudo docker compose run --rm
  app pytest` (API-level smoke) and curl the served HTML/JS for sanity; list
  what the qa-agent must verify in a real browser.
- Do not run git commands.
- Final message: compact digest — files, self-check results, open questions.
