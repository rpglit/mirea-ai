# ADR-0006: Error handling

Status: Accepted (2026-10-02)

## Context

All three intake channels must reject bad input with readable, structured
errors (FR-001 c3: malformed text names the problem and creates no net;
FR-002 c3: schema violations are listed; FR-003 c3–4: the form rejects bad
names, weights, and counts server-side as well), and later stages fail in
typed ways: cap aborts (NFR-002 c2), unknown sessions (FR-022 c4), and
disabled transitions (FR-017 c1). Design brief §6 pins the hierarchy, the
HTTP mapping, the body shape, and the logging rule; the domain layer stays
framework-free, so domain code raises typed exceptions and only the API
layer translates them to HTTP.

## Decision

All typed errors are defined in `petrinet/errors.py`:

```python
class PetriNetError(Exception):
    """Base class for all typed application errors."""

class ParseError(PetriNetError):
    """position: char offset in the raw text; message: human-readable cause."""
    position: int
    message: str

class ValidationError(PetriNetError):
    """problems: list of {"path": <JSON/text path>, "message": <cause>}."""
    problems: list[dict[str, str]]

class UnknownSessionError(PetriNetError):
    """session_id: the id that was not found."""
    session_id: str

class CapExceededError(PetriNetError):
    """limit: the REACH_MAX_MARKINGS value that was exceeded."""
    limit: int

class TransitionNotEnabledError(PetriNetError):
    """marking: current marking tuple; transition: the requested name."""
    marking: tuple[int, ...]
    transition: str
```

Message formats (for `str()`/logging): `parse error at position {position}:
{message}`; `validation failed ({n} problems)`; `unknown session:
{session_id}`; `reachability cap exceeded: more than {limit} markings`;
`transition '{transition}' is not enabled at marking {marking}`.

HTTP mapping, applied once at the API layer:

| Exception | Status | error.code |
| --------- | ------ | ---------- |
| `ParseError`, `ValidationError` | 422 | `parse_failed` / `validation_failed` |
| `UnknownSessionError` | 404 | `unknown_session` |
| `CapExceededError` | 413 | `cap_exceeded` |
| `TransitionNotEnabledError` | 409 | `transition_not_enabled` |
| anything else (uncaught) | 500 | `internal_error` |

Every error body is `{"error": {"code", "message", "details?"}}` (deterministic key order); one concrete example per status:

- 422: `{"error": {"code": "validation_failed", "message": "JSON input failed validation (1 problem)", "details": [{"path": "initial_marking", "message": "missing entry for place 'p4'"}]}}`
- 404: `{"error": {"code": "unknown_session", "message": "unknown session: a3f2c81d90b44e7f8c6d5e4b3a291807", "details": {"session_id": "a3f2c81d90b44e7f8c6d5e4b3a291807"}}}`
- 413: `{"error": {"code": "cap_exceeded", "message": "more than 50000 markings; build the coverability tree instead", "details": {"limit": 50000, "suggestion": "coverability"}}}`
- 409: `{"error": {"code": "transition_not_enabled", "message": "transition 't4' is not enabled at marking (5, 5, 2, 5, 4, 3)", "details": {"transition": "t4", "marking": [5, 5, 2, 5, 4, 3]}}}`

Logging (NFR-003): each error is logged as one JSON line carrying `session_id` (or `null`), `error_code`, and `duration_ms` alongside `timestamp`, `level`, `message`; user input is echoed at most as its 200-character prefix; no secrets ever appear in logs.

Placement: FastAPI exception handlers for all five classes are registered in `create_app()` and build the bodies above. Domain modules (`petrinet/parser`, `petrinet/core`, `petrinet/reachability`, `petrinet/properties`, `petrinet/storage` — the component names of ARCHITECTURE.md) only raise these exceptions — they never import FastAPI or raise `HTTPException`. Uncaught exceptions fall through to the 500 handler, which logs the traceback and returns `internal_error`.

## Consequences

- Domain code stays framework-free and unit-testable: tests assert exception types and attributes; the HTTP mapping is tested once via TestClient.
- One body shape lets the UI render a single error panel (NFR-006: `message` is shown to the user in Russian, `code` drives client behavior).
- The 413 `details.suggestion` powers the mandated switch to coverability mode after a cap abort (NFR-002 c3, FR-006 c4); the 404 satisfies FR-022 c4 (typed 404 after session deletion).
- The 200-char input prefix keeps error logs bounded and grep-able without persisting full user input at ERROR level.
- Adding a new typed error later is a three-line change — subclass, table row,
  handler — keeping the mapping exhaustive and documented in one place.
- Known deviation (documented, accepted in the Phase-4.4 review): pydantic
  schema-level rejects (e.g. a wrong `format` literal) and truly unexpected
  exceptions use FastAPI's native bodies (`{"detail": ...}` 422 / plain-text
  500) rather than the ADR body; the five domain error classes always produce
  the ADR body, and error log lines carry `error_code`, `session_id`, and
  `duration_ms` (middleware-stamped).
