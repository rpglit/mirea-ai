"""API routes (contract: ARCHITECTURE.md 'API routes')."""

from __future__ import annotations

import json
import signal
import threading
from typing import Literal, cast

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from petrinet import parser, solvers
from petrinet.config import Settings, get_settings
from petrinet.core import Marking, PetriNet, minimal_marking
from petrinet.errors import (
    TransitionNotEnabledError,
    UnknownSessionError,
    UnsupportedModelError,
    ValidationError,
)
from petrinet.properties import Report, analyze, is_coverable, is_reachable, sequence_report
from petrinet.reachability import build
from petrinet.storage import (
    SessionStore,
    marking_from_list,
    marking_to_list,
    model_from_json,
    model_to_json,
    steps_from_json,
    steps_to_json,
    structure_from_json,
    structure_to_json,
)

_store: SessionStore | None = None


def get_store() -> SessionStore:
    """Return the process-wide SessionStore, created on demand and cached in ``_store``.

    The store opens the SQLite database at ``get_settings().db_path``. Tests may
    replace ``petrinet.api.routes._store`` directly with a preconfigured store.
    """
    global _store
    if _store is None:
        settings: Settings = get_settings()
        _store = SessionStore(settings.db_path)
    return _store


class ParseRequest(BaseModel):
    """POST /parse request body (contract: ARCHITECTURE.md 'API routes').

    Example (text format, smoke net, REQUIREMENTS §5.1):

        {"format": "text", "payload": "S = (P, T, I, O, µ),\nP = {p1, ...}, T = {t1, ...}"}
    """

    format: Literal["text", "json", "form"]
    payload: str | dict[str, object]
    name: str | None = None


def _load_session(store: SessionStore, session_id: str) -> dict[str, str | None]:
    """Return the full session row for ``session_id`` (all 9 columns).

    Example: ``row = _load_session(store, sid)``.

    Raises:
        UnknownSessionError: the session id is unknown (deleted or never created);
            the API layer maps it to the typed 404 response.
    """
    row = store.get_session(session_id)
    if row is None:
        raise UnknownSessionError(session_id)
    return row


def _arc_maps(net: PetriNet) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """Canonical arc maps {transition: {place: weight}} for API responses.

    Example (smoke net): ``{"t1": {"p1": 2}, "t2": {"p1": 1, "p6": 1}, ...}``.
    """
    inputs = {
        t: {p: w for p, w in arcs} for t, arcs in zip(net.transitions, net.inputs, strict=True)
    }
    outputs = {
        t: {p: w for p, w in arcs} for t, arcs in zip(net.transitions, net.outputs, strict=True)
    }
    return inputs, outputs


def _parse_to_net(body: ParseRequest) -> PetriNet:
    """Parse the request payload with the channel named by ``body.format``.

    Returns the frozen net produced by the matching intake function. No session
    is created on any failure (FR-001..FR-003 c3).

    Raises:
        ValidationError: the payload container does not match the channel —
            a string for ``text`` and an object for ``json``/``form``.
        ParseError: malformed raw text (``text`` channel only).
    """
    if body.format == "text":
        if not isinstance(body.payload, str):
            raise ValidationError(
                [{"path": "payload", "message": "payload must be a string for text format"}]
            )
        return parser.parse_text(body.payload)
    if not isinstance(body.payload, dict):
        raise ValidationError(
            [{"path": "payload", "message": "payload must be an object for json/form format"}]
        )
    if body.format == "json":
        return parser.parse_json(body.payload)
    return parser.parse_form(body.payload)


router = APIRouter()


@router.post("/parse", status_code=201)
def parse(body: ParseRequest) -> dict[str, object]:
    """Parse a net description and create its session; respond 201 with the session id.

    Smoke request (text format, REQUIREMENTS §5.1) and response (201):

        {
            "format": "text",
            "payload": "S = (P, T, I, O, µ),\\n
                       P = {p1, p2, p3, p4, p5, p6}, T = {t1, t2, t3, t4, t5},\\n
                       I(t1) = {p1, p1}, O(t1) = {p2},\\n
                       I(t2) = {p1, p6}, O(t2) = {p3, p3},\\n
                       I(t3) = {p2}, O(t3) = {p4, p4, p4},\\n
                       I(t4) = {p2, p3, p4, p4}, O(t4) = {p5, p6},\\n
                       I(t5) = {p5, p5}, O(t5) = {p1, p3},\\n
                       µ = (7, 4, 2, 5, 4, 3)."
        }

        {
            "initial_marking": [7, 4, 2, 5, 4, 3],
            "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
            "session_id": "00000000000000000000000000000001",
            "transitions": ["t1", "t2", "t3", "t4", "t5"]
        }

    The stored session starts at the initial marking with an empty step history
    (ADR-0005); no graph or report is computed here. Errors: 422 ``parse_failed``
    (ParseError), 422 ``validation_failed`` (ValidationError).
    """
    net = _parse_to_net(body)
    store = get_store()
    session_id = store.create_session(body.name, body.format, model_to_json(net))
    store.set_state(session_id, json.dumps(marking_to_list(net.initial_marking)), steps_to_json([]))
    response: dict[str, object] = {
        "initial_marking": marking_to_list(net.initial_marking),
        "inputs": _arc_maps(net)[0],
        "outputs": _arc_maps(net)[1],
        "places": list(net.places),
        "session_id": session_id,
        "transitions": list(net.transitions),
    }
    if net.inhibitors is not None:
        response["inhibitors"] = {
            t: list(p) for t, p in zip(net.transitions, net.inhibitors, strict=True)
        }
    if net.priorities is not None:
        response["priorities"] = {
            t: pr for t, pr in zip(net.transitions, net.priorities, strict=True)
        }
    if net.delays is not None:
        response["delays"] = {
            t: [[p, tau] for p, tau in arcs]
            for t, arcs in zip(net.transitions, net.delays, strict=True)
            if arcs
        }
    if net.colors is not None:
        response["colors"] = {
            "initial_values": net.colors.initial_values,
            "guards": net.colors.guards,
            "output_exprs": net.colors.output_exprs,
        }
    return response


class GraphRequest(BaseModel):
    """POST /graph request body (contract: ARCHITECTURE.md 'API routes').

    Example (smoke net; ``mode`` omitted -> ``"auto"``):

        {"session_id": "00000000000000000000000000000001"}
    """

    session_id: str
    mode: Literal["auto", "bounded", "coverability"] = "auto"


class PropertiesWith(BaseModel):
    """Optional additions to the /properties report (ARCH section 2.6).

    Example: ``{"matrices": true, "mu_min": true, "sequence": ["t1", "t2"]}``.
    """

    matrices: bool = False
    mu_min: bool = False
    sequence: list[str] | None = None


class PropertiesRequest(BaseModel):
    """POST /properties request body (contract: ARCHITECTURE.md 'API routes').

    Example (smoke net, FR-010 fixture query; a null value skips the answer):

        {
            "session_id": "00000000000000000000000000000001",
            "queries": {"reachable_marking": [7, 4, 2, 5, 4, 3]}
        }
    """

    session_id: str
    queries: dict[str, list[int] | None] | None = None
    with_: PropertiesWith | None = Field(default=None, alias="with")


def _report_to_dict(report: Report) -> dict[str, object]:
    """Convert a property report to the contract's JSON shape (keys sorted).

    Matches the 'Sample properties report' block of ARCHITECTURE.md:
    ``deadlocks`` as marking lists (omega -> null) and ``stats`` remapped to
    ``edge_count``/``node_count``; the ``/properties`` endpoint adds the
    ``queries`` block (sorted, between ``per_place_k`` and ``safe``) only
    when the request carried queries. Example (smoke net, D-009..D-013):

        {
            "approximation": null,
            "bounded": true,
            "dead_transitions": [],
            "deadlock_free": false,
            "deadlocks": [[0, 0, 0, 0, 1, 10], [0, 0, 1, 5, 0, 9]],
            "global_k": 29,
            "home_state": false,
            "liveness": {"level": "L1", "transitions": {"t1": {"level": "L1", "occurs": true}}},
            "per_place_k": {"p1": 10, "p2": 8, "p3": 16, "p4": 29, "p5": 8, "p6": 10},
            "safe": false,
            "stats": {"edge_count": 4983, "node_count": 1503}
        }
    """
    return {
        "approximation": report.approximation,
        "bounded": report.bounded,
        "dead_transitions": report.dead_transitions,
        "deadlock_free": report.deadlock_free,
        "deadlocks": [marking_to_list(m) for m in report.deadlocks],
        "global_k": report.global_k,
        "home_state": report.home_state,
        "liveness": {
            "level": report.liveness.level,
            "transitions": {
                t: {"level": tl.level, "occurs": tl.occurs}
                for t, tl in report.liveness.transitions.items()
            },
        },
        "per_place_k": report.per_place_k,
        "safe": report.safe,
        "stats": {"edge_count": report.stats["edges"], "node_count": report.stats["nodes"]},
        "conservative": report.conservative,
        "verdict": report.verdict,
        "mu_min": report.mu_min,
    }


@router.post("/graph")
def graph(body: GraphRequest) -> dict[str, object]:
    """Build and store the reachability structure; respond with its JSON form.

    Request (``mode`` omitted -> ``"auto"``, smoke net) and response (200):

        {"session_id": "00000000000000000000000000000001"}

        {
            "capped": false,
            "edge_count": 4983,
            "kind": "graph",
            "node_count": 1503,
            "structure": {
                "edges": [["n0", "t1", "n1"], ["n0", "t2", "n2"], ["n0", "t3", "n3"]],
                "nodes": [
                    ["n0", [7, 4, 2, 5, 4, 3]],
                    ["n1", [5, 5, 2, 5, 4, 3]],
                    ["n2", [6, 4, 4, 5, 4, 2]]
                ]
            }
        }

    The example abbreviates ``structure``; the real response carries all nodes
    and edges in deterministic order (ADR-0002). The structure is stored on
    the session (ADR-0005) and reused by ``/properties``, ``/goto`` and the
    exports. Errors: 404 ``unknown_session``, 413 ``cap_exceeded``.
    """
    store = get_store()
    row = _load_session(store, body.session_id)
    net = model_from_json(cast(str, row["model_json"]))
    structure = build(net, mode=body.mode, cap=get_settings().reach_max_markings)
    store.set_graph(body.session_id, structure_to_json(structure))
    return {
        "capped": False,
        "edge_count": structure.stats["edges"],
        "kind": structure.kind,
        "node_count": structure.stats["nodes"],
        "structure": {
            "edges": [list(e) for e in structure.edges],
            "nodes": [[nid, marking_to_list(m)] for nid, m in structure.nodes],
        },
    }


@router.post("/properties")
def properties(body: PropertiesRequest) -> dict[str, object]:
    """Analyze the stored structure; respond with the report plus query answers.

    Request (smoke net, FR-010 fixture) and response (200, report abbreviated):

        {
            "queries": {"reachable_marking": [11, 0, 0, 0, 0, 0]},
            "session_id": "00000000000000000000000000000001"
        }

        {
            "approximation": null,
            "bounded": true,
            "queries": {"is_reachable": {"11,0,0,0,0,0": false}},
            "safe": false,
            "stats": {"edge_count": 4983, "node_count": 1503}
        }

    The full report is the 'Sample properties report' of ARCHITECTURE.md (see
    :func:`_report_to_dict`); ``queries`` is present only when the request
    carried queries (``is_reachable`` answers null on a coverability tree).
    Errors: 404 ``unknown_session``, 422 ``validation_failed`` (no stored
    graph, unknown query key, wrong marking length).
    """
    store = get_store()
    row = _load_session(store, body.session_id)
    graph_json = row["graph_json"]
    if graph_json is None:
        raise ValidationError(
            [{"path": "session", "message": "graph not built; call /graph first"}]
        )
    structure = structure_from_json(graph_json)
    net = model_from_json(cast(str, row["model_json"]))
    with_ = body.with_
    report = analyze(net, structure, with_mu_min=bool(with_ and with_.mu_min))
    store.set_report(body.session_id, json.dumps(_report_to_dict(report), sort_keys=True))
    result: dict[str, object] = _report_to_dict(report)
    if with_ is not None:
        if with_.matrices:
            if net.colors is not None:
                raise UnsupportedModelError("colors")
            w_minus, w_plus, w = net.incidence()
            result["matrices"] = {"W": w, "W_minus": w_minus, "W_plus": w_plus}
        if with_.sequence is not None:
            current = _as_marking(json.loads(cast(str, row["current_marking"])))
            try:
                seq_report = sequence_report(net, current, with_.sequence)
            except ValueError as exc:
                raise ValidationError([{"path": "with.sequence", "message": str(exc)}]) from exc
            result["sequence"] = seq_report
    if body.queries:
        answers: dict[str, object] = {}
        for key, values in body.queries.items():
            if key not in ("reachable_marking", "coverable_marking"):
                raise ValidationError([{"path": f"queries.{key}", "message": "unknown query"}])
            if values is None:
                continue
            target = tuple(values)
            if len(target) != len(net.places):
                raise ValidationError(
                    [{"path": f"queries.{key}", "message": f"expected {len(net.places)} values"}]
                )
            answer: bool | None = (
                is_reachable(net, structure, target)
                if key == "reachable_marking"
                else is_coverable(net, structure, target)
            )
            label = "is_reachable" if key == "reachable_marking" else "is_coverable"
            answers[label] = {",".join(str(v) for v in values): answer}
        result["queries"] = {label: answers[label] for label in sorted(answers)}
    return {key: result[key] for key in sorted(result)}


class SolveRequest(BaseModel):
    """POST /solve request body (contract: ARCHITECTURE.md section 2.6).

    Example (catalog task, no user data needed):

        {"task_id": "TASK-PN-05"}

    Example (custom task with a net):

        {"task_id": "custom:firing", "data": {"net": {...}, "sequence": ["t1"]}}
    """

    task_id: str
    data: dict[str, object] | None = None


@router.post("/solve")
async def solve_task(body: SolveRequest) -> dict[str, object]:
    """Solve one methodic (or custom) task; respond with the Report.

    Stateless: no session is required or created (ARCH section 2.6). The
    response is the methodic report ``{task_id, given, find, solution,
    answer, notes}`` (keys sorted). The computation is bounded by
    ``SOLVER_TIMEOUT_S`` (30 s) via SIGALRM on the main thread (the async
    endpoint runs there); a breach answers 500 ``solver_failed``. Errors:
    422 ``unknown_task``, 422 ``validation_failed``, 413 ``cap_exceeded``,
    422 ``unsupported_model``, 409 ``conflict``, 500 ``solver_failed``.
    """
    from petrinet.errors import SolverError
    from petrinet.solvers import SOLVER_TIMEOUT_S

    def _on_timeout(signum: int, frame: object) -> None:
        raise SolverError(f"таймаут: вычисления превысили {SOLVER_TIMEOUT_S} с")

    previous: object = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGALRM, _on_timeout)
        signal.alarm(SOLVER_TIMEOUT_S)
    try:
        report = solvers.solve(body.task_id, body.data)
    finally:
        if previous is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)  # type: ignore[arg-type]
    return report.to_dict()


@router.get("/catalog")
def catalog_endpoint(group: str | None = None) -> list[dict[str, object]]:
    """Return the solver catalog, optionally filtered by group (PN/LSS/FA).

    Response (200), 71 entries without a filter:

        [
            {
                "group": "PN",
                "input_kind": "pn",
                "prefill": {"net": {...}, "sequence": ["t1", "t2", "t3", "t4", "t5"]},
                "source": "семинар 2, стр. 1, Задание 1",
                "task_id": "TASK-PN-05",
                "title": "Эталонная сеть 6×5 (µ=(7,4,2,5,4,3))",
                "type": "задание"
            }
        ]

    ``prefill`` — the methodic default data for the task form (FR-332);
    ``null`` when the task has no built-in data.

    Errors: 422 ``unknown_task`` (unknown group).
    """
    return [
        {
            "task_id": t.task_id,
            "group": t.group,
            "title": t.title,
            "source": t.source,
            "type": t.type,
            "input_kind": t.input_kind,
            "prefill": solvers.prefill(t.task_id),
        }
        for t in solvers.catalog(group)
    ]


class MatricesRequest(BaseModel):
    """POST /matrices request body. Example: ``{"session_id": "<id>"}``."""

    session_id: str


@router.post("/matrices")
def matrices(body: MatricesRequest) -> dict[str, list[list[int]]]:
    """Return the W−/W+/W matrices (rows = places, columns = transitions).

    Errors: 404 ``unknown_session``, 422 ``unsupported_model`` (colors).
    """
    store = get_store()
    row = _load_session(store, body.session_id)
    net = model_from_json(cast(str, row["model_json"]))
    if net.colors is not None:
        raise UnsupportedModelError("colors")
    w_minus, w_plus, w = net.incidence()
    return {"W": w, "W_minus": w_minus, "W_plus": w_plus}


class MinimalMarkingRequest(BaseModel):
    """POST /minimal-marking request body.

    Example: ``{"session_id": "<id>", "parallel": false}``.
    """

    session_id: str
    parallel: bool = False


@router.post("/minimal-marking")
def minimal_marking_endpoint(body: MinimalMarkingRequest) -> dict[str, object]:
    """Return the minimal marking (M6) and the per-transition requirements.

    ``parallel`` switches to the worst-case sum of all input requirements.
    Errors: 404 ``unknown_session``, 422 ``unsupported_model`` (colors).
    """
    store = get_store()
    row = _load_session(store, body.session_id)
    net = model_from_json(cast(str, row["model_json"]))
    if net.colors is not None:
        raise UnsupportedModelError("colors")
    per_transition = {
        t: [sum(ww for p, ww in arcs if p == p_) for p_ in net.places]
        for t, arcs in zip(net.transitions, net.inputs, strict=True)
    }
    return {
        "mu_min": list(minimal_marking(net, parallel=body.parallel)),
        "per_transition": per_transition,
    }


class FireRequest(BaseModel):
    """POST /fire request body (contract: ARCHITECTURE.md 'API routes').

    Examples (smoke net): fire ``t1`` at µ0, undo that step, reset the session:

        {"session_id": "00000000000000000000000001", "action": "fire", "transition": "t1"}
        {"session_id": "00000000000000000000000001", "action": "undo"}
        {"session_id": "00000000000000000000000001", "action": "reset"}
    """

    session_id: str
    action: Literal["fire", "undo", "reset"]
    transition: str | None = None


class GotoRequest(BaseModel):
    """POST /goto request body (contract: ARCHITECTURE.md 'API routes').

    Example (switch the smoke session to the first ``t3`` child of µ0):

        {"session_id": "00000000000000000000000001", "marking": [7, 3, 2, 8, 4, 3]}
    """

    session_id: str
    marking: list[int]


def _as_marking(values: object) -> Marking:
    """Validate a stored marking array and return it as a concrete Marking.

    The stored interactive state is always concrete: it starts at µ0 and only
    ``/fire`` and ``/goto`` update it, with integer vectors (ADR-0005) — so a
    missing entry or a ``null`` (omega) coordinate is corruption, not a state.

    Example: ``current = _as_marking(json.loads(row["current_marking"]))``.

    Raises:
        ValidationError: the value is not an array of integers.
    """
    if not isinstance(values, list):
        raise ValidationError([{"path": "session", "message": "stored marking is corrupt"}])
    marking = marking_from_list(values)
    if None in marking:
        raise ValidationError([{"path": "session", "message": "stored marking is corrupt"}])
    return cast("Marking", marking)


def _fire_response(
    net: PetriNet, current: Marking, history: list[dict[str, object]]
) -> dict[str, object]:
    """Build the ``/fire`` and ``/goto`` response: new state plus history tail.

    ``history_tail`` is the last recorded step (empty after ``reset``); the
    ``/state`` endpoint returns the full history and does not use this helper.
    Example (smoke net after firing ``t1`` at µ0, D-014):

        {
            "active_transitions": ["t1", "t2", "t3", "t4", "t5"],
            "current_marking": [5, 5, 2, 5, 4, 3],
            "history_tail": [
                {"from": [7, 4, 2, 5, 4, 3], "to": [5, 5, 2, 5, 4, 3], "transition": "t1"}
            ]
        }
    """
    return {
        "active_transitions": net.active(current),
        "current_marking": marking_to_list(current),
        "history_tail": history[-1:],
    }


@router.post("/fire")
def fire(body: FireRequest) -> dict[str, object]:
    """Apply a state operation (``fire`` | ``undo`` | ``reset``); respond with the new state.

    Request (fire ``t1`` at µ0 of the smoke net) and response (200, D-014):

        {
            "action": "fire",
            "session_id": "00000000000000000000000001",
            "transition": "t1"
        }

        {
            "active_transitions": ["t1", "t2", "t3", "t4", "t5"],
            "current_marking": [5, 5, 2, 5, 4, 3],
            "history_tail": [
                {"from": [7, 4, 2, 5, 4, 3], "to": [5, 5, 2, 5, 4, 3], "transition": "t1"}
            ]
        }

    Semantics (ADR-0005): ``fire`` appends the step ``{"kind": "fire",
    "transition", "from", "to"}``; ``undo`` pops the last step and restores its
    ``from`` marking; ``reset`` restores µ0 and clears the history (empty tail).
    Errors: 404 ``unknown_session``, 422 ``validation_failed`` (missing
    ``transition``, empty history, corrupt stored state), 409
    ``transition_not_enabled``.
    """
    store = get_store()
    row = _load_session(store, body.session_id)
    net = model_from_json(cast(str, row["model_json"]))
    current = _as_marking(json.loads(cast(str, row["current_marking"])))
    history = steps_from_json(cast(str, row["history_json"]))
    if body.action == "fire":
        if body.transition is None:
            raise ValidationError(
                [{"path": "transition", "message": "transition is required for action 'fire'"}]
            )
        if not net.enabled(current, body.transition):
            raise TransitionNotEnabledError(current, body.transition)
        new = net.fire(current, body.transition)
        history.append(
            {
                "kind": "fire",
                "transition": body.transition,
                "from": marking_to_list(current),
                "to": marking_to_list(new),
            }
        )
        current = new
    elif body.action == "undo":
        if not history:
            raise ValidationError([{"path": "session", "message": "no steps to undo"}])
        step = history.pop()
        current = _as_marking(step.get("from"))
    else:
        current = net.initial_marking
        history = []
    store.set_state(body.session_id, json.dumps(marking_to_list(current)), steps_to_json(history))
    return _fire_response(net, current, history)


@router.post("/goto")
def goto(body: GotoRequest) -> dict[str, object]:
    """Switch the session to a node of the stored reachability graph; respond with the new state.

    Request (the first ``t3`` child of µ0 of the smoke net) and response (200);
    a goto step is recorded with ``transition`` null (ADR-0005):

        {
            "marking": [7, 3, 2, 8, 4, 3],
            "session_id": "00000000000000000000000001"
        }

        {
            "active_transitions": ["t1", "t2", "t3", "t4", "t5"],
            "current_marking": [7, 3, 2, 8, 4, 3],
            "history_tail": [
                {"from": [7, 4, 2, 5, 4, 3], "to": [7, 3, 2, 8, 4, 3], "transition": null}
            ]
        }

    The target must be an exact node of the stored structure: the graph is
    built first, and omega coordinates are never addressed. Errors: 404
    ``unknown_session``, 422 ``validation_failed`` (no stored graph, or the
    marking is not a node of it).
    """
    store = get_store()
    row = _load_session(store, body.session_id)
    net = model_from_json(cast(str, row["model_json"]))
    current = _as_marking(json.loads(cast(str, row["current_marking"])))
    graph_json = row["graph_json"]
    if graph_json is None:
        raise ValidationError(
            [{"path": "session", "message": "graph not built; call /graph first"}]
        )
    structure = structure_from_json(graph_json)
    target = tuple(body.marking)
    if len(target) != len(net.places) or target not in {m for _nid, m in structure.nodes}:
        raise ValidationError(
            [
                {
                    "path": "marking",
                    "message": "marking is not a node of the stored reachability graph",
                }
            ]
        )
    history = steps_from_json(cast(str, row["history_json"]))
    history.append(
        {
            "kind": "goto",
            "transition": None,
            "from": marking_to_list(current),
            "to": list(target),
        }
    )
    current = target
    store.set_state(body.session_id, json.dumps(marking_to_list(current)), steps_to_json(history))
    return _fire_response(net, current, history)


@router.get("/state/{session_id}")
def state(session_id: str) -> dict[str, object]:
    """Return the full interactive state of a session.

    Response (200) for a fresh smoke session; ``history`` is the complete step
    list, unlike ``/fire`` and ``/goto``, which reply with ``history_tail``:

        {
            "active_transitions": ["t1", "t2", "t3", "t4", "t5"],
            "current_marking": [7, 4, 2, 5, 4, 3],
            "history": []
        }

    Errors: 404 ``unknown_session``.
    """
    store = get_store()
    row = _load_session(store, session_id)
    net = model_from_json(cast(str, row["model_json"]))
    current = _as_marking(json.loads(cast(str, row["current_marking"])))
    history = steps_from_json(cast(str, row["history_json"]))
    return {
        "active_transitions": net.active(current),
        "current_marking": marking_to_list(current),
        "history": history,
    }


@router.get("/sessions")
def list_sessions(limit: int = 50) -> list[dict[str, object]]:
    """Return the session summaries (newest first), at most ``limit`` rows.

    ``limit`` defaults to 50 (BUG-9); values below 1 are rejected. Response
    (200); the model is read back from the stored ``model_json`` without
    re-validation (FR-022):

        [
            {
                "created_at": "2026-10-02T12:00:00+00:00",
                "name": "smoke",
                "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
                "session_id": "00000000000000000000000000000001",
                "transitions": ["t1", "t2", "t3", "t4", "t5"]
            }
        ]

    Errors: 422 ``validation_failed`` (limit < 1), 500 ``internal_error``.
    """
    if limit < 1:
        raise ValidationError([{"path": "limit", "message": "limit должен быть не меньше 1"}])
    store = get_store()
    result: list[dict[str, object]] = []
    for row in store.list_sessions()[:limit]:
        model_raw: dict[str, object] = json.loads(cast(str, row["model_json"]))
        result.append(
            {
                "created_at": row["created_at"],
                "name": row["name"],
                "places": model_raw.get("places"),
                "session_id": row["id"],
                "transitions": model_raw.get("transitions"),
            }
        )
    return result


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, object]:
    """Return the full stored summary of one session.

    Response (200) for a smoke session after ``/graph`` and ``/properties``:

        {
            "created_at": "2026-10-02T12:00:00+00:00",
            "current_marking": [7, 4, 2, 5, 4, 3],
            "graph_built": true,
            "input_format": "text",
            "name": "smoke",
            "places": ["p1", "p2", "p3", "p4", "p5", "p6"],
            "report_computed": true,
            "session_id": "00000000000000000000000000000001",
            "transitions": ["t1", "t2", "t3", "t4", "t5"]
        }

    ``graph_built``/``report_computed`` flag whether the stored artifacts
    exist (null -> false); ``current_marking`` is the live interactive state.
    Errors: 404 ``unknown_session``.
    """
    store = get_store()
    row = _load_session(store, session_id)
    model_raw: dict[str, object] = json.loads(cast(str, row["model_json"]))
    return {
        "created_at": row["created_at"],
        "current_marking": json.loads(cast(str, row["current_marking"])),
        "graph_built": row["graph_json"] is not None,
        "input_format": row["input_format"],
        "inputs": model_raw.get("inputs"),
        "name": row["name"],
        "outputs": model_raw.get("outputs"),
        "places": model_raw.get("places"),
        "report_computed": row["report_json"] is not None,
        "session_id": session_id,
        "transitions": model_raw.get("transitions"),
    }


@router.get("/sessions/{session_id}/graph")
def get_stored_graph(session_id: str) -> dict[str, object]:
    """Return the stored reachability structure without recomputing it.

    Used by the UI to restore a session from history (FR-022): the response
    has the same shape as ``POST /graph`` (minus ``capped``).

    Response (200) for a built smoke session:

        {
            "edge_count": 4983,
            "kind": "graph",
            "node_count": 1503,
            "structure": {"edges": [["n0", "t1", "n1"]], "nodes": [["n0", [7, 4, 2, 5, 4, 3]]]}
        }

    Errors: 404 ``unknown_session``, 422 ``validation_failed`` (not built).
    """
    store = get_store()
    row = _load_session(store, session_id)
    graph_json = row["graph_json"]
    if graph_json is None:
        raise ValidationError(
            [{"path": "session", "message": "graph not built; call /graph first"}]
        )
    structure = structure_from_json(graph_json)
    return {
        "edge_count": structure.stats["edges"],
        "kind": structure.kind,
        "node_count": structure.stats["nodes"],
        "structure": {
            "edges": [list(e) for e in structure.edges],
            "nodes": [[nid, marking_to_list(m)] for nid, m in structure.nodes],
        },
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> Response:
    """Hard-delete a session; respond 204 with no body.

    The row (model, artifacts, state) is removed permanently (FR-022 c4).
    Errors: 404 ``unknown_session``.
    """
    store = get_store()
    if not store.delete_session(session_id):
        raise UnknownSessionError(session_id)
    return Response(status_code=204)


@router.get("/sessions/{session_id}/export/report")
def export_report(session_id: str) -> Response:
    """Download the stored properties report as a JSON file attachment.

    Response: 200 ``application/json`` with ``Content-Disposition:
    attachment; filename="report.json"`` — the exact bytes stored by
    ``/properties`` (keys sorted). Errors: 404 ``unknown_session``, 422
    ``validation_failed`` (no stored report).
    """
    store = get_store()
    row = _load_session(store, session_id)
    report_json = row["report_json"]
    if report_json is None:
        raise ValidationError(
            [{"path": "session", "message": "report not computed; call /properties first"}]
        )
    return Response(
        content=report_json,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="report.json"'},
    )


def _marking_csv_value(v: int | None) -> str:
    """Render one marking coordinate in the CSV export (omega rendered as "omega")."""
    return "omega" if v is None else str(v)


@router.get("/sessions/{session_id}/export/markings")
def export_markings(session_id: str) -> Response:
    """Download the stored reachable markings as a CSV file attachment.

    Response: 200 ``text/csv`` with ``Content-Disposition:
    attachment; filename="markings.csv"``; header = place names in declared
    order, then one row per node in BFS discovery order (µ0 first), values in
    declared place order, omega rendered as "omega". Deterministic
    byte-for-byte. Errors: 404 ``unknown_session``, 422 ``validation_failed``
    (no stored graph).
    """
    store = get_store()
    row = _load_session(store, session_id)
    graph_json = row["graph_json"]
    if graph_json is None:
        raise ValidationError(
            [{"path": "session", "message": "graph not built; call /graph first"}]
        )
    structure = structure_from_json(graph_json)
    model_raw: dict[str, object] = json.loads(cast(str, row["model_json"]))
    places: list[str] = cast(list[str], model_raw["places"])
    lines: list[str] = [",".join(places)]
    for _node_id, marking in structure.nodes:
        lines.append(",".join(_marking_csv_value(v) for v in marking))
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="markings.csv"'},
    )
