"""SQLite session storage: one ingested net plus its stored analyses (ADR-0005).

A session row holds the parsed net (canonical model JSON, ADR-0001 shape),
the artifacts computed later — reachability structure (``graph_json``) and
properties report (``report_json``), both NULL until their endpoint runs —
and the interactive state (``current_marking`` + ``history_json``). Storing
the artifacts instead of recomputing them lets a session reopen without
re-running the reachability build, and a volume-mounted DB file survives
container restarts (FR-022).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from uuid import uuid4

from petrinet.core import PetriNet
from petrinet.parser import canonical_to_net
from petrinet.reachability import MarkingOrOmega, ReachableStructure

_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,  -- uuid4 hex
    name            TEXT NOT NULL,
    created_at      TEXT NOT NULL,     -- ISO 8601 UTC
    input_format    TEXT NOT NULL,     -- "text" | "json" | "form"
    model_json      TEXT NOT NULL,     -- parsed net (ADR-0001 shape)
    graph_json      TEXT,              -- reachability structure; NULL until /graph
    report_json     TEXT,              -- properties report; NULL until /properties
    current_marking TEXT NOT NULL,     -- JSON array of token counts, declared place order
    history_json    TEXT NOT NULL      -- JSON array of {transition, from, to}; initially "[]"
);
"""

_SESSION_COLUMNS = (
    "id, name, created_at, input_format, model_json, "
    "graph_json, report_json, current_marking, history_json"
)


def model_to_json(net: PetriNet) -> str:
    """Serialize a net to the canonical model JSON (ADR-0001/ADR-0003 shape).

    Example (smoke net):
        model_to_json(smoke)
        '{"inputs":{"t1":{"p1":2},"t2":{},...},"outputs":{...},...,"places":["p1",...],...}'
    """
    payload: dict[str, object] = {
        "places": list(net.places),
        "transitions": list(net.transitions),
        "inputs": {t: dict(arcs) for t, arcs in zip(net.transitions, net.inputs, strict=True)},
        "outputs": {t: dict(arcs) for t, arcs in zip(net.transitions, net.outputs, strict=True)},
        "initial_marking": dict(zip(net.places, net.initial_marking, strict=True)),
    }
    if net.inhibitors is not None:
        payload["inhibitors"] = {
            t: list(p) for t, p in zip(net.transitions, net.inhibitors, strict=True)
        }
    if net.priorities is not None:
        payload["priorities"] = {
            t: pr for t, pr in zip(net.transitions, net.priorities, strict=True)
        }
    if net.delays is not None:
        payload["delays"] = {
            t: dict(arcs)
            for t, arcs in zip(net.transitions, net.delays, strict=True)
            if arcs
        }
    if net.colors is not None:
        payload["colors"] = {
            "initial_values": net.colors.initial_values,
            "guards": net.colors.guards,
            "output_exprs": net.colors.output_exprs,
        }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def model_from_json(raw: str) -> PetriNet:
    """Parse canonical model JSON back to the frozen net (inverse of :func:`model_to_json`).

    Example: ``net = model_from_json(model_to_json(smoke))``.
    """
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("model json must be an object")
    return canonical_to_net(payload)


def structure_to_json(structure: ReachableStructure) -> str:
    """Serialize a reachability structure to compact JSON.

    Nodes are ``[id, marking array]`` pairs (``null`` marks an omega
    coordinate), edges are ``[src, transition, dst]`` triples.

    Example: ``structure_to_json(build(smoke, "auto"))`` starts with
    ``'{"edges":[["n0","t1","n1"],...],"kind":"graph","nodes":[["n0",[7,4,2,5,4,3]],...]'``.
    """
    payload: dict[str, object] = {
        "kind": structure.kind,
        "nodes": [[node_id, marking_to_list(marking)] for node_id, marking in structure.nodes],
        "edges": [[src, transition, dst] for src, transition, dst in structure.edges],
        "stats": dict(structure.stats),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def structure_from_json(raw: str) -> ReachableStructure:
    """Rebuild a reachability structure from its JSON form (inverse of :func:`structure_to_json`).

    Raises:
        ValueError: malformed payload (wrong container types, unknown kind,
            non-integer marking or stats values).
    """
    payload: object = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("structure json must be an object")
    kind: object = payload.get("kind")
    if kind not in ("graph", "coverability"):
        raise ValueError("structure kind must be 'graph' or 'coverability'")

    raw_nodes: object = payload.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("structure nodes must be an array")
    nodes: list[tuple[str, MarkingOrOmega]] = []
    for entry in raw_nodes:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("each structure node must be [id, marking array]")
        node_id: object = entry[0]
        raw_marking: object = entry[1]
        if not isinstance(node_id, str) or not isinstance(raw_marking, list):
            raise ValueError("structure node id must be a string and its marking an array")
        nodes.append((node_id, marking_from_list(_marking_values(raw_marking))))

    raw_edges: object = payload.get("edges")
    if not isinstance(raw_edges, list):
        raise ValueError("structure edges must be an array")
    edges: list[tuple[str, str, str]] = []
    for entry in raw_edges:
        if not isinstance(entry, list) or len(entry) != 3:
            raise ValueError("each structure edge must be [src, transition, dst]")
        src: object = entry[0]
        transition: object = entry[1]
        dst: object = entry[2]
        if not (isinstance(src, str) and isinstance(transition, str) and isinstance(dst, str)):
            raise ValueError("structure edge entries must be strings")
        edges.append((src, transition, dst))

    raw_stats: object = payload.get("stats")
    if not isinstance(raw_stats, dict):
        raise ValueError("structure stats must be an object")
    stats: dict[str, int] = {}
    for key, value in raw_stats.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("structure stats values must be integers")
        stats[key] = value
    return ReachableStructure(kind=kind, nodes=nodes, edges=edges, stats=stats)


def marking_to_list(marking: MarkingOrOmega) -> list[int | None]:
    """Convert a marking to its JSON array form (declared place order).

    Example: ``marking_to_list((7, 4, 2)) == [7, 4, 2]``.
    """
    return [int(value) if value is not None else None for value in marking]


def marking_from_list(values: list[int | None]) -> MarkingOrOmega:
    """Convert a JSON marking array back to a marking (inverse of :func:`marking_to_list`).

    ``None`` entries stay ``None`` (omega); every other entry is an integer.

    Example: ``marking_from_list([1, None]) == (1, None)``.
    """
    return tuple(int(value) if value is not None else None for value in values)


def _marking_values(raw: list[object]) -> list[int | None]:
    """Validate a JSON marking array and return its values (null stays None)."""
    values: list[int | None] = []
    for value in raw:
        if value is None:
            values.append(None)
        elif isinstance(value, int) and not isinstance(value, bool):
            values.append(value)
        else:
            raise ValueError("marking values must be integers or null")
    return values


def steps_from_json(raw: str) -> list[dict[str, object]]:
    """Parse a stored step history (FR-017) back to a list of step objects.

    Stored steps have kind ``"fire"`` or ``"goto"`` (undo pops the last step,
    reset clears the history — ADR-0005); each step is
    ``{"kind": ..., "transition": str|null, "from": [ints], "to": [ints]}``
    with the marking before and after the step.

    Example: ``steps_from_json("[]") == []``.

    Raises:
        ValueError: payload is not an array of objects.
    """
    payload: object = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("step history must be an array")
    steps: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ValueError("each history step must be an object")
        steps.append(entry)
    return steps


def steps_to_json(steps: list[dict[str, object]]) -> str:
    """Serialize a step history to compact JSON (inverse of :func:`steps_from_json`).

    Example: ``steps_to_json([]) == "[]"``.
    """
    return json.dumps(steps, sort_keys=True, separators=(",", ":"))


class SessionStore:
    """Thread-safe SQLite session store: one row per ingested net (ADR-0005).

    A single ``sqlite3`` connection (``check_same_thread=False``) with every
    read/write under one ``RLock`` — no WAL, no pooling; the store assumes a
    single-process server (one uvicorn worker).

    Example:
        store = SessionStore("/data/sessions.db")
        sid = store.create_session("smoke", "text", model_to_json(net))
    """

    def __init__(self, db_path: str) -> None:
        """Open the sessions database at ``db_path`` (created if missing) and ensure the schema.

        Creates the ``sessions`` table per the ADR-0005 DDL and stamps
        ``PRAGMA user_version = 1``.

        Example: ``SessionStore("/data/sessions.db")``.
        """
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute(_SESSIONS_DDL)
            self._conn.execute("PRAGMA user_version = 1")
            self._conn.commit()

    def create_session(self, name: str | None, input_format: str, model_json: str) -> str:
        """Insert a new session in its post-parse state; return the new id (uuid4 hex).

        ``created_at`` is the current UTC time (ISO 8601); ``name`` falls back
        to ``"session-<first 8 id chars>"``; ``current_marking`` is the
        model's initial marking in declared place order; ``history_json``
        starts as ``"[]"``; ``graph_json`` and ``report_json`` are NULL.

        Example: ``sid = store.create_session("smoke", "text", model_json)``.
        """
        session_id = uuid4().hex
        session_name = name or f"session-{session_id[:8]}"
        created_at = datetime.now(UTC).isoformat()
        initial_marking = json.dumps(
            list(model_from_json(model_json).initial_marking), separators=(",", ":")
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions "
                "(id, name, created_at, input_format, model_json, current_marking, history_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    session_name,
                    created_at,
                    input_format,
                    model_json,
                    initial_marking,
                    "[]",
                ),
            )
            self._conn.commit()
        return session_id

    def get_session(self, session_id: str) -> dict[str, str | None] | None:
        """Return the full session row (all 9 columns) as a dict, or None if the id is unknown.

        The API layer converts None into the typed 404 error.

        Example: ``row = store.get_session(sid)``.
        """
        with self._lock:
            cursor = self._conn.execute(
                f"SELECT {_SESSION_COLUMNS} FROM sessions WHERE id = ?", (session_id,)
            )
            row: sqlite3.Row | None = cursor.fetchone()
        if row is None:
            return None
        return dict(zip(row.keys(), row, strict=True))

    def list_sessions(self) -> list[dict[str, str | None]]:
        """Return every session row (all 9 columns), newest first.

        Ordering: ``created_at DESC`` with ``id DESC`` as the tie-breaker.

        Example: ``rows = store.list_sessions()``.
        """
        with self._lock:
            cursor = self._conn.execute(
                f"SELECT {_SESSION_COLUMNS} FROM sessions ORDER BY created_at DESC, id DESC"
            )
            rows: list[sqlite3.Row] = cursor.fetchall()
        return [dict(zip(row.keys(), row, strict=True)) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        """Hard-delete a session row; return True if a row was removed.

        Deletion is permanent: the row disappears from ``list_sessions`` and
        its step history is unrecoverable (FR-022 c4).

        Example: ``deleted = store.delete_session(sid)``.
        """
        with self._lock:
            cursor = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def set_model(self, session_id: str, model_json: str) -> None:
        """Replace the stored model of a session.

        Example: ``store.set_model(sid, model_to_json(net))``.
        """
        self._update_column("model_json", session_id, model_json)

    def set_graph(self, session_id: str, graph_json: str) -> None:
        """Store the computed reachability structure of a session.

        Example: ``store.set_graph(sid, structure_to_json(structure))``.
        """
        self._update_column("graph_json", session_id, graph_json)

    def set_report(self, session_id: str, report_json: str) -> None:
        """Store the computed properties report of a session.

        Example: ``store.set_report(sid, report_json)``.
        """
        self._update_column("report_json", session_id, report_json)

    def set_state(self, session_id: str, current_marking_json: str, history_json: str) -> None:
        """Replace the interactive state (current marking + step history) of a session.

        Example: ``store.set_state(sid, current_marking_json, history_json)``.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET current_marking = ?, history_json = ? WHERE id = ?",
                (current_marking_json, history_json, session_id),
            )
            self._conn.commit()

    def close(self) -> None:
        """Close the database connection.

        Example: ``store.close()``.
        """
        with self._lock:
            self._conn.close()

    def _update_column(self, column: str, session_id: str, value: str) -> None:
        """Run one ``UPDATE sessions SET <column> = ? WHERE id = ?`` (no existence check)."""
        with self._lock:
            self._conn.execute(
                f"UPDATE sessions SET {column} = ? WHERE id = ?", (value, session_id)
            )
            self._conn.commit()
