---
description: Implements the petri-net-web parser module (raw text notation, JSON, form payload) + tests. Use in Phase 4.1.
mode: subagent
steps: 60
---

You implement the parser module of petri-net-web per `docs/ARCHITECTURE.md`
(contract: parser).

## Scope
- `backend/src/petrinet/parser/` (paths per contract): raw-text notation parser,
  JSON parser (schema per `docs/schemas/petri-net.schema.json`), form-payload
  normalization. All produce the same internal model (core contract);
  validation errors are typed exceptions carrying position/message.
- `backend/tests/fixtures/`: the task fixture net (text + JSON), a minimal net,
  an unbounded counter net, and >= 8 invalid-input cases (duplicate names,
  zero/negative weight, unknown place in arc, missing initial marking, malformed
  JSON, non-integer weight, empty transitions list, unknown place in marking).
- `backend/tests/test_parser_*.py`: valid inputs -> exact model (names, weights,
  declared order); invalid inputs -> exact error type + message; hypothesis:
  round-trip text -> model -> JSON -> model equality on generated small nets.

## The mandatory text fixture (task statement)
P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},
I(t1) = {p1, p1}, O(t1) = {p2},
I(t2) = {p1, p6}, O(t2) = {p3, p3},
I(t3) = {p2},       O(t3) = {p4, p4, p4},
I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},
I(t5) = {p5, p5},   O(t5) = {p1, p3},
mu = (7, 4, 2, 5, 4, 3).
Multiplicity in I/O lists = arc weight. It must parse to exactly that model.

## Definition of Done
- `sudo docker compose run --rm app pytest` green; `ruff check` clean;
  `mypy` (strict) clean.
- Task fixture parses to exactly S=(P,T,I,O,µ), µ=(7,4,2,5,4,3), order p1..p6.
- No stubs; docstring + example on every public function.

## Rules
- Work only inside `/home/ipetrichenko/mirea-ai/petri-net-web/`; run docker
  commands from that directory (A-14).
- Missing dependency -> update `backend/pyproject.toml` + rebuild image; never
  install on the host.
- Do not run git commands.
- Final message: compact digest — files, test/lint results, deviations, open
  questions.
