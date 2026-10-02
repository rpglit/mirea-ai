"""Net description intake: raw text, JSON, and form channels (FR-001..FR-003).

All three channels normalize to one canonical JSON object (ADR-0003) and share
the same two-pass validator, so equivalent descriptions produce the same
frozen ``PetriNet`` (ADR-0001).

Smoke net (REQUIREMENTS 5.1/5.2): all three channels yield P = p1..p6,
T = t1..t5, mu0 = (7, 4, 2, 5, 4, 3).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import jsonschema

from petrinet.core import PetriNet
from petrinet.errors import ParseError, ValidationError

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PT_RE = re.compile(
    r"^\s*P\s*=\s*\{(?P<places>[^}]*)\}\s*,\s*T\s*=\s*\{(?P<transitions>[^}]*)\}\s*,?\s*$"
)
_IO_RE = re.compile(
    r"^\s*I\s*\(\s*(?P<t1>" + _NAME + r")\s*\)\s*=\s*\{(?P<inner_in>[^}]*)\}\s*,\s*"
    r"O\s*\(\s*(?P<t2>" + _NAME + r")\s*\)\s*=\s*\{(?P<inner_out>[^}]*)\}\s*,?\s*$"
)
_MARK_RE = re.compile(r"^\s*(?:µ|μ|mu)\s*=\s*\((?P<values>[^)]*)\)\s*\.\s*$")
_HEADER_RE = re.compile(r"^\s*S\s*=")


def _problem(path: str, message: str) -> dict[str, str]:
    """Build one validation problem entry ``{"path": ..., "message": ...}``."""
    return {"path": path, "message": message}


@lru_cache(maxsize=1)
def _schema() -> dict[str, object]:
    """Load the JSON Schema 2020-12 document shipped with the package (ADR-0003)."""
    raw: object = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError([_problem("$", "schema.json must be a JSON object")])
    return raw


def validate_canonical(payload: dict[str, object]) -> dict[str, object]:
    """Validate a canonical net description (two-pass, ADR-0003).

    Pass 1 runs the JSON Schema; pass 2 enforces the cross-field rules the
    schema cannot express (marking covers all places exactly, arc references
    are declared). ALL problems are collected and raised in one
    ``ValidationError``. Returns the normalized payload: absent ``inputs`` /
    ``outputs`` keys and absent per-transition entries become empty maps, and
    the marking is aligned to the declared places.

    Example:
        >>> parse_json(SMOKE_JSON)  # doctest: +SKIP
        PetriNet(places=('p1', 'p2', ...), initial_marking=(7, 4, 2, 5, 4, 3), ...)
    """
    problems: list[dict[str, str]] = []
    validator = jsonschema.Draft202012Validator(_schema())
    for err in sorted(
        validator.iter_errors(payload), key=lambda e: [str(p) for p in e.absolute_path]
    ):
        path = ".".join(str(p) for p in err.absolute_path) or "$"
        problems.append(_problem(path, str(err.message)))

    places = payload.get("places")
    transitions = payload.get("transitions")
    if isinstance(places, list) and isinstance(transitions, list):
        place_set = {str(p) for p in places if isinstance(p, str)}
        transition_set = {str(t) for t in transitions if isinstance(t, str)}
        marking = payload.get("initial_marking")
        if isinstance(marking, dict):
            marked = {str(k) for k in marking}
            for missing in sorted(place_set - marked):
                problems.append(
                    _problem("initial_marking", f"missing entry for place '{missing}'")
                )
            for extra in sorted(marked - place_set):
                problems.append(_problem("initial_marking", f"unknown place '{extra}'"))
        for key in ("inputs", "outputs"):
            arcs = payload.get(key)
            if isinstance(arcs, dict):
                for t, entry in arcs.items():
                    if not isinstance(t, str) or t not in transition_set:
                        problems.append(_problem(f"{key}.{t}", "unknown transition"))
                        continue
                    if isinstance(entry, dict):
                        for p in entry:
                            if not isinstance(p, str) or p not in place_set:
                                problems.append(_problem(f"{key}.{t}.{p}", "unknown place"))

    if problems:
        raise ValidationError(problems)
    if not isinstance(places, list) or not isinstance(transitions, list):
        raise ValidationError([_problem("$", "places/transitions must be arrays")])

    places_list = [str(p) for p in places]
    transitions_list = [str(t) for t in transitions]

    def arc_map(key: str) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        raw = payload.get(key)
        if isinstance(raw, dict):
            for t, entry in raw.items():
                if not isinstance(t, str) or not isinstance(entry, dict):
                    continue
                for p, w in entry.items():
                    if isinstance(p, str) and isinstance(w, int) and not isinstance(w, bool):
                        result.setdefault(t, {})[p] = w
        return result

    inputs = arc_map("inputs")
    outputs = arc_map("outputs")
    marking = payload.get("initial_marking")
    normalized_marking: dict[str, object] = {}
    for p in places_list:
        value = marking.get(p) if isinstance(marking, dict) else None
        normalized_marking[p] = value if isinstance(value, int) else 0

    return {
        "places": places_list,
        "transitions": transitions_list,
        "inputs": {t: inputs.get(t, {}) for t in transitions_list},
        "outputs": {t: outputs.get(t, {}) for t in transitions_list},
        "initial_marking": normalized_marking,
    }


def canonical_to_net(payload: dict[str, object]) -> PetriNet:
    """Convert a validated canonical description to the frozen PetriNet model.

    Arcs of each transition are sorted by the declared place index, so the
    result is deterministic regardless of JSON key order.

    Example (smoke net, REQUIREMENTS 5.2):
        >>> net = canonical_to_net(validate_canonical(SMOKE_JSON))  # doctest: +SKIP
        >>> net.initial_marking
        (7, 4, 2, 5, 4, 3)
    """
    places_raw = payload.get("places")
    transitions_raw = payload.get("transitions")
    inputs_raw = payload.get("inputs")
    outputs_raw = payload.get("outputs")
    marking_raw = payload.get("initial_marking")
    if not (
        isinstance(places_raw, list)
        and isinstance(transitions_raw, list)
        and isinstance(inputs_raw, dict)
        and isinstance(outputs_raw, dict)
        and isinstance(marking_raw, dict)
    ):
        raise ValidationError([_problem("$", "canonical payload is malformed")])

    places = [str(p) for p in places_raw]
    transitions = [str(t) for t in transitions_raw]
    place_index = {p: i for i, p in enumerate(places)}

    def arcs_of(raw: dict[object, object], t: str) -> tuple[tuple[str, int], ...]:
        entry = raw.get(t)
        pairs: list[tuple[str, int]] = []
        if isinstance(entry, dict):
            for p, w in entry.items():
                if isinstance(p, str) and isinstance(w, int) and not isinstance(w, bool):
                    pairs.append((p, w))
        return tuple(sorted(pairs, key=lambda pw: place_index[pw[0]]))

    marking: list[int] = []
    for p in places:
        value = marking_raw.get(p)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(
                [_problem(f"initial_marking.{p}", "token count must be an integer")]
            )
        marking.append(value)

    return PetriNet(
        places=tuple(places),
        transitions=tuple(transitions),
        inputs=tuple(arcs_of(inputs_raw, t) for t in transitions),
        outputs=tuple(arcs_of(outputs_raw, t) for t in transitions),
        initial_marking=tuple(marking),
    )


def parse_json(payload: dict[str, object]) -> PetriNet:
    """Parse the canonical JSON object (FR-002, ADR-0003).

    Example (smoke net, REQUIREMENTS 5.2):
        >>> net = parse_json(SMOKE_JSON)  # doctest: +SKIP
        >>> net.places
        ('p1', 'p2', 'p3', 'p4', 'p5', 'p6')

    Raises:
        ValidationError: schema or cross-field violations (all problems listed).
    """
    return canonical_to_net(validate_canonical(payload))


def parse_form(payload: dict[str, object]) -> PetriNet:
    """Parse a form intake payload (FR-003) into the canonical form.

    Pinned shape (D-029)::

        {
          "places": ["p1", "p2"],
          "transitions": ["t1"],
          "arcs": [
            {"source": "p1", "target": "t1", "weight": 2, "direction": "input"},
            {"source": "t1", "target": "p2", "weight": 1, "direction": "output"}
          ],
          "initial_marking": {"p1": 0, "p2": 0}
        }

    ``direction`` "input": source is a place, target a transition; "output":
    source a transition, target a place. Duplicate arcs are validation errors.

    Raises:
        ValidationError: bad arc entries, duplicates, or shared-validator
        violations (all problems listed).
    """
    problems: list[dict[str, str]] = []
    inputs: dict[str, dict[str, int]] = {}
    outputs: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, str, str]] = set()

    arcs = payload.get("arcs")
    if not isinstance(arcs, list):
        problems.append(_problem("arcs", "arcs must be a list"))
        arcs = []
    for i, arc in enumerate(arcs):
        if not isinstance(arc, dict):
            problems.append(_problem(f"arcs.{i}", "arc must be an object"))
            continue
        source = arc.get("source")
        target = arc.get("target")
        weight = arc.get("weight")
        direction = arc.get("direction")
        if not isinstance(source, str):
            problems.append(_problem(f"arcs.{i}.source", "source must be a name string"))
            continue
        if not isinstance(target, str):
            problems.append(_problem(f"arcs.{i}.target", "target must be a name string"))
            continue
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 1:
            problems.append(
                _problem(f"arcs.{i}.weight", "weight must be a positive integer")
            )
            continue
        if not isinstance(direction, str) or direction not in ("input", "output"):
            problems.append(
                _problem(f"arcs.{i}.direction", "direction must be 'input' or 'output'")
            )
            continue
        key = (direction, source, target)
        if key in seen:
            problems.append(_problem(f"arcs.{i}", f"duplicate arc {source}->{target}"))
            continue
        seen.add(key)
        if direction == "input":
            inputs.setdefault(target, {})[source] = weight
        else:
            outputs.setdefault(source, {})[target] = weight

    if problems:
        raise ValidationError(problems)

    canonical: dict[str, object] = {
        "places": payload.get("places", []),
        "transitions": payload.get("transitions", []),
        "inputs": inputs,
        "outputs": outputs,
        "initial_marking": payload.get("initial_marking", {}),
    }
    return canonical_to_net(validate_canonical(canonical))


def _line_spans(text: str) -> list[tuple[int, str]]:
    """Return ``(offset, line)`` for every line of ``text``."""
    spans: list[tuple[int, str]] = []
    pos = 0
    for line in text.split("\n"):
        spans.append((pos, line))
        pos += len(line) + 1
    return spans


def _inner_start(line: str, which: int) -> int:
    """Absolute-in-line offset just after the ``which``-th (0-based) ``{``."""
    start = -1
    for _ in range(which + 1):
        start = line.find("{", start + 1)
        if start == -1:
            return 0
    return start + 1


def _split_items(inner: str) -> list[tuple[str, int]]:
    """Comma-separated items of a brace interior as ``(item, offset-in-inner)``."""
    items: list[tuple[str, int]] = []
    pos = 0
    for chunk in inner.split(","):
        item = chunk.strip()
        if item:
            items.append((item, pos + chunk.index(item)))
        pos += len(chunk) + 1
    return items


def _parse_names(
    inner: str,
    base: int,
    kind: str,
    declared: list[str] | None = None,
    repeat_ok: bool = False,
) -> list[str]:
    """Parse identifier items; ``base`` is the absolute offset of ``inner[0]``.

    Raises ParseError at the offending token for invalid, undeclared, or
    (when ``repeat_ok`` is False) duplicated names.
    """
    names: list[str] = []
    for item, inner_off in _split_items(inner):
        offset = base + inner_off
        if not re.fullmatch(_NAME, item):
            raise ParseError(offset, f"invalid {kind} name '{item}'")
        if not repeat_ok and item in names:
            raise ParseError(offset, f"duplicate {kind} name '{item}'")
        if declared is not None and item not in declared:
            raise ParseError(offset, f"unknown {kind} '{item}'")
        names.append(item)
    return names


def parse_text(text: str) -> PetriNet:
    """Parse the raw mathematical notation (FR-001).

    Line grammar (blank lines ignored): an optional ``S = (...)`` header, then
    ``P = {...}, T = {...}``, then one ``I(t) = {...}, O(t) = {...}`` line per
    declared transition, then ``µ = (v1, ..., vn)`` (``mu`` accepted too). A
    name repeated k times inside an I/O set is an arc of weight k.

    Example (smoke net, REQUIREMENTS 5.1):
        >>> net = parse_text(SMOKE_TEXT)  # doctest: +SKIP
        >>> net.initial_marking
        (7, 4, 2, 5, 4, 3)

    Raises:
        ParseError: any syntax problem, with the character position.
        ValidationError: cross-field problems caught by the shared validator.
    """
    significant = [(off, line) for off, line in _line_spans(text) if line.strip()]
    if not significant:
        raise ParseError(0, "empty description")

    pos = 0
    if _HEADER_RE.match(significant[0][1]):
        pos = 1
    if pos >= len(significant):
        raise ParseError(significant[0][0], "missing 'P = {...}, T = {...}' line")

    line_off, line = significant[pos]
    match = _PT_RE.match(line)
    if match is None:
        raise ParseError(line_off, "expected 'P = {...}, T = {...}'")
    places = _parse_names(match.group("places"), line_off + _inner_start(line, 0), "place")
    transitions = _parse_names(
        match.group("transitions"), line_off + _inner_start(line, 1), "transition"
    )
    pos += 1

    if pos >= len(significant):
        raise ParseError(line_off + len(line), "missing 'µ = (...)' marking line")

    inputs: dict[str, Counter[str]] = {}
    outputs: dict[str, Counter[str]] = {}
    for mid_off, mid_line in significant[pos:-1]:
        io = _IO_RE.match(mid_line)
        if io is None or io.group("t1") != io.group("t2"):
            raise ParseError(mid_off, "expected 'I(t) = {...}, O(t) = {...}'")
        t = io.group("t1")
        if t not in transitions:
            raise ParseError(mid_off, f"unknown transition '{t}'")
        if t in inputs:
            raise ParseError(mid_off, f"duplicate I/O line for transition '{t}'")
        inputs[t] = Counter(
            _parse_names(
                io.group("inner_in"),
                mid_off + _inner_start(mid_line, 0),
                "place",
                places,
                repeat_ok=True,
            )
        )
        outputs[t] = Counter(
            _parse_names(
                io.group("inner_out"),
                mid_off + _inner_start(mid_line, 1),
                "place",
                places,
                repeat_ok=True,
            )
        )

    mark_off, mark_line = significant[-1]
    mv = _MARK_RE.match(mark_line)
    if mv is None:
        raise ParseError(mark_off, "expected 'µ = (v1, ..., vn)'")
    values: list[int] = []
    values_base = mark_off + mark_line.index("(") + 1
    for token, inner_off in _split_items(mv.group("values")):
        if not re.fullmatch(r"\d+", token):
            raise ParseError(values_base + inner_off, f"non-integer marking value '{token}'")
        values.append(int(token))
    if len(values) != len(places):
        raise ParseError(
            mark_off, f"marking has {len(values)} values, expected {len(places)}"
        )

    missing = [t for t in transitions if t not in inputs]
    if missing:
        raise ParseError(mark_off, f"missing I/O line for transition '{missing[0]}'")

    canonical: dict[str, object] = {
        "places": places,
        "transitions": transitions,
        "inputs": {t: dict(inputs[t]) for t in transitions},
        "outputs": {t: dict(outputs[t]) for t in transitions},
        "initial_marking": {p: v for p, v in zip(places, values, strict=True)},
    }
    return canonical_to_net(validate_canonical(canonical))
