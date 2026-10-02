# ADR-0003: JSON input schema

Note (2026-10-02, D-028): the runtime source of truth is the package file
`backend/src/petrinet/schema.json` (loaded by `petrinet/parser.py`);
`docs/schemas/petri-net.schema.json` is the documented mirror and must be kept
in sync (the parser-agent verifies byte-equality in a test).

Status: Accepted (2026-10-02)

## Context

FR-002 requires JSON intake; the task statement defers the schema to the
architecture phase, and design brief §3 pins the shape: `places`, `transitions`,
`inputs`, `outputs`, `initial_marking` with identifier names, arc weights ≥ 1,
and full-place marking coverage. Raw text and form intake normalize to this
model, so this JSON object is the single canonical form shared by all three
intake channels.

## Decision

The input is one JSON object, validated in two passes.

Pass 1 — JSON-Schema-2020-12 skeleton (the machine-readable file
`docs/schemas/petri-net.schema.json` is emitted in a follow-up task and must
match this skeleton exactly):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["places", "transitions", "initial_marking"],
  "additionalProperties": false,
  "properties": {
    "places": {"type": "array", "minItems": 1, "uniqueItems": true,
               "items": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"}},
    "transitions": {"type": "array", "minItems": 1, "uniqueItems": true,
                    "items": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"}},
    "inputs": {"$ref": "#/$defs/arc_map"},
    "outputs": {"$ref": "#/$defs/arc_map"},
    "initial_marking": {"type": "object", "minProperties": 1,
                        "$comment": "must cover ALL places — enforced by pass 2, not by this schema",
                        "propertyNames": {"pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
                        "additionalProperties": {"type": "integer", "minimum": 0}}
  },
  "$defs": {
    "arc_map": {"type": "object",
                "propertyNames": {"pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
                "additionalProperties": {"type": "object",
                                         "propertyNames": {"pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
                                         "additionalProperties": {"type": "integer", "minimum": 1}}}
  }
}
```

Pass 2 — cross-field rules plain JSON Schema cannot express (it cannot relate
keys of one field to the values of another); run by the same validator and
reported in the same error format:

- arc-reference uniqueness: every `inputs`/`outputs` key must be a declared
  transition and every inner key a declared place;
- marking coverage: `initial_marking` keys must be exactly the declared
  places — a missing place is a validation error, not an implicit 0
  (REQUIREMENTS §8 item 4); surplus keys are errors too.

Absent top-level `inputs`/`outputs` normalize to empty maps, and a declared
transition missing from them gets an empty arc map (weight-0 arcs) —
REQUIREMENTS §8 item 8; the same normalization applies to form intake and is
test-covered.

Any failure from either pass is rejected with HTTP 422:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "JSON input failed validation (2 problems)",
    "details": [
      {"path": "inputs.t9", "message": "unknown transition 't9'"},
      {"path": "initial_marking", "message": "missing entry for place 'p4'"}
    ]
  }
}
```

## Consequences

- One validator for all channels: raw text (FR-001) and form (FR-003)
  normalize to this JSON and share both passes, so every intake mode yields
  identical 422 bodies (brief §3, §6).
- `docs/schemas/petri-net.schema.json` is produced in a follow-up task and must match the pass-1 skeleton above exactly; it is the reference for pass 1.
- Pass 2 is O(|P| + |T|), negligible against graph construction (NFR-001).
- Unparseable JSON uses the same 422 shape; no session is created on any
  validation failure (FR-002 criterion 3).
