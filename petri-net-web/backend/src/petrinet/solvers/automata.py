"""Finite automaton model and operations (ARCH section 2.5.3).

An automaton is ``A = <P, S, s0, phi[, W, psi]>``: ``P`` — input alphabet,
``S`` — states, ``s0`` — initial state, ``phi: P x S -> S`` — transition
function, ``W`` — output alphabet, ``psi`` — output function (Moore:
``S -> W``, keyed by state; Mealy: ``P x S -> W``, keyed by ``(state, input)``).
The transition function may be given in any of the three methodic ways
(enumeration, table, graph); :func:`normalize` builds the single internal
representation. All functions are pure; errors are
``petrinet.errors.ValidationError``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from petrinet.errors import ValidationError


@dataclass(frozen=True)
class Automaton:
    """A complete finite automaton (``phi`` defined for every ``si x pj``).

    Example (Moore, methodic TASK-FA-03)::

        Automaton(
            P=("p1", "p2"), S=("s0", "s1", "s2", "s3"), s0="s0",
            phi={("s0", "p1"): "s0", ("s0", "p2"): "s1", ...},
            W=("w0", "w1"), psi={"s0": "w0", "s1": "w1", "s2": "w0", "s3": "w0"},
            kind="moore",
        )
    """

    P: tuple[str, ...]
    S: tuple[str, ...]
    s0: str
    phi: dict[tuple[str, str], str]  # (state, input) -> next state
    W: tuple[str, ...] | None = None
    psi: dict[Any, str] | None = None  # Moore: {si: wi}; Mealy: {(si, pj): wi}
    kind: str = "none"  # "none" | "moore" | "mealy"


def _phi_from_spec(spec: Any, S: Sequence[str], P: Sequence[str]) -> dict[tuple[str, str], str]:
    """Extract ``phi`` from enumeration / table / graph (methodic, 3 ways)."""
    phi: dict[tuple[str, str], str] = {}
    if isinstance(spec, list):  # enumeration: triples [si, pj, sk]
        for row in spec:
            si, pj, sk = (str(x) for x in row)
            phi[(si, pj)] = sk
    elif isinstance(spec, dict):
        if "table" in spec:  # rows: [si, sk(p1), sk(p2), ...] in order of P
            for row in spec["table"]:
                si = str(row[0])
                for pj, cell in zip(P, row[1:], strict=False):
                    if pj is None:
                        continue
                    phi[(si, pj)] = str(cell)
        elif "graph" in spec:  # edges: [si, pj, sk]
            for row in spec["graph"].get("edges", []):
                si, pj, sk = (str(x) for x in row)
                phi[(si, pj)] = sk
        else:
            raise ValidationError(
                [{"path": "phi", "message": "нужен список троек, table или graph"}]
            )
    else:
        raise ValidationError(
            [{"path": "phi", "message": "нужен список троек, table или graph"}]
        )
    for si in S:
        for pj in P:
            if (si, pj) not in phi:
                raise ValidationError(
                    [
                        {
                            "path": "phi",
                            "message": f"неполная функция перехода: нет пары ({si}, {pj})",
                        }
                    ]
                )
    return phi


def normalize(input_spec: dict[str, Any]) -> Automaton:
    """Build an ``Automaton`` from a spec (ARCH section 4.3).

    Example::

        normalize({"P": ["p1", "p2"], "S": ["s0", "s1"], "s0": "s0",
                   "type": "none",
                   "phi": [["s0", "p1", "s0"], ["s0", "p2", "s1"],
                            ["s1", "p1", "s1"], ["s1", "p2", "s0"]]})
    """
    problems: list[dict[str, str]] = []
    P = tuple(str(x) for x in input_spec.get("P", []))
    S = tuple(str(x) for x in input_spec.get("S", []))
    s0 = str(input_spec.get("s0", ""))
    kind = str(input_spec.get("type", "none"))
    if kind not in ("none", "moore", "mealy"):
        raise ValidationError([{"path": "type", "message": f"неизвестный тип автомата: {kind}"}])
    if not P:
        problems.append({"path": "P", "message": "пустой входной алфавит"})
    if not S:
        problems.append({"path": "S", "message": "пустое множество состояний"})
    if s0 and s0 not in S:
        problems.append({"path": "s0", "message": f"начальное состояние {s0} не входит в S"})
    if problems:
        raise ValidationError(problems)

    phi = _phi_from_spec(input_spec["phi"], S, P)
    for (si, pj), sk in phi.items():
        if sk not in S:
            raise ValidationError(
                [
                    {
                        "path": "phi",
                        "message": f"переход ({si}, {pj}) ведёт в неизвестное состояние {sk}",
                    }
                ]
            )

    W: tuple[str, ...] | None = None
    psi: dict[Any, str] | None = None
    if kind in ("moore", "mealy"):
        W = tuple(str(x) for x in input_spec.get("W", []))
        raw = input_spec.get("psi")
        if raw is None:
            raise ValidationError([{"path": "psi", "message": "нет функции выхода"}])
        if kind == "moore":
            psi = {str(k): str(v) for k, v in dict(raw).items()}
            for si in S:
                if si not in psi:
                    raise ValidationError(
                        [{"path": "psi", "message": f"нет выхода для состояния {si}"}]
                    )
                if psi[si] not in W:
                    raise ValidationError(
                        [{"path": "psi", "message": f"выход {psi[si]} не входит в W"}]
                    )
        else:  # mealy
            psi = {(str(a), str(b)): str(c) for a, b, c in [tuple(x) for x in raw]}
            for si in S:
                for pj in P:
                    if (si, pj) not in psi:
                        raise ValidationError(
                            [{"path": "psi", "message": f"нет выхода для пары ({si}, {pj})"}]
                        )
                    if psi[(si, pj)] not in W:
                        raise ValidationError(
                            [
                                {
                                    "path": "psi",
                                    "message": f"выход {psi[(si, pj)]} не входит в W",
                                }
                            ]
                        )
    return Automaton(P=P, S=S, s0=s0, phi=phi, W=W, psi=psi, kind=kind)


def to_enumeration(a: Automaton) -> list[str]:
    """Return the «перечисление»: equalities ``sk = φ(si, pj)`` (+ ``ψ``).

    Example: ``to_enumeration(moore3)`` -> ``['s0 = φ(s0, p1)', ..., 'w1 = ψ(s1)']``.
    """
    lines = [f"{a.phi[(si, pj)]} = φ({si}, {pj})" for si in a.S for pj in a.P]
    if a.kind == "moore" and a.psi is not None:
        lines += [f"{a.psi[si]} = ψ({si})" for si in a.S]
    elif a.kind == "mealy" and a.psi is not None:
        lines += [f"{a.psi[(si, pj)]} = ψ({si}, {pj})" for si in a.S for pj in a.P]
    return lines


def to_table(a: Automaton) -> dict[str, Any]:
    """Return the transition table (rows — states, columns — ``P``).

    Moore adds the output column (``si/wi``); Mealy merges ``sk/wi`` cells
    (methodic tables 1.4 / 1.9).
    """
    rows: list[list[str]] = []
    for si in a.S:
        cells = [a.phi[(si, pj)] for pj in a.P]
        if a.kind == "moore" and a.psi is not None:
            rows.append([f"{si}/{a.psi[si]}", *cells])
        elif a.kind == "mealy" and a.psi is not None:
            rows.append(
                [si, *[f"{c}/{a.psi[(si, pj)]}" for c, pj in zip(cells, a.P, strict=True)]]
            )
        else:
            rows.append([si, *cells])
    return {"cols": list(a.P), "rows": rows}


def to_graph(a: Automaton) -> dict[str, Any]:
    """Return the oriented graph: vertices ``si[/wi]``, arcs ``pk[/wq]``."""
    nodes = [
        [si, a.psi[si] if a.kind == "moore" and a.psi is not None else None] for si in a.S
    ]
    edges: list[list[str]] = []
    for si in a.S:
        for pj in a.P:
            sk = a.phi[(si, pj)]
            row = [si, pj, sk]
            if a.kind == "mealy" and a.psi is not None:
                row.append(a.psi[(si, pj)])
            edges.append(row)
    return {"s0": a.s0, "nodes": nodes, "edges": edges}


def simulate(a: Automaton, word: Sequence[str]) -> dict[str, Any]:
    """Simulate processing of ``word`` by automaton ticks ``t0..tn``.

    Moore: the output at ``t0`` is ``ψ(s0)`` and does NOT enter the output
    word (methodic: «w0* не учитывается»); ``w(t+1) = ψ(s(t+1))``.
    Mealy: ``t0`` has no output; ``w(t+1) = ψ(s(t), p(t))``.
    Example::

        simulate(moore3, ["p1", "p2"]) ->
        {"states": ["s0", "s0", "s1"],
         "output_word": ["w0", "w1"],
         "ticks": [["t0", "s0", None, "w0*"], ["t1", "s0", "p1", "w0"],
                    ["t2", "s1", "p2", "w1"]]}
    """
    states: list[str] = [a.s0]
    current = a.s0
    output_word: list[str] = []
    ticks: list[list[Any]] = []
    if a.kind == "moore" and a.psi is not None:
        ticks.append(["t0", a.s0, None, f"{a.psi[a.s0]}*"])
    else:
        ticks.append(["t0", a.s0, None, None])
    for idx, p in enumerate(word, start=1):
        if p not in a.P:
            raise ValidationError([{"path": "word", "message": f"символ {p} не входит в P"}])
        prev = current
        current = a.phi[(prev, p)]
        states.append(current)
        if a.kind == "moore" and a.psi is not None:
            out = a.psi[current]
            output_word.append(out)
        elif a.kind == "mealy" and a.psi is not None:
            out = a.psi[(prev, p)]
            output_word.append(out)
        else:
            out = None
        ticks.append([f"t{idx}", current, p, out])
    return {"ticks": ticks, "states": states, "output_word": output_word}


def compare(a1: Automaton, a2: Automaton, word: Sequence[str]) -> dict[str, Any]:
    """Process one word by both automata and compare output words."""
    r1 = simulate(a1, word)
    r2 = simulate(a2, word)
    equal = r1["output_word"] == r2["output_word"]
    note = (
        "У обоих автоматов одно и то же входное слово перерабатывается в "
        "совпадающее выходное слово. Разница: в автомате Мура выходной символ "
        "можно считывать сразу после установки в начальное состояние (символ t0 "
        "определяется начальным состоянием и не является реакцией на вход), в "
        "автомате Мили — после установки в начальное состояние и подачи первого "
        "входного символа."
        if equal
        else "Выходные слова различаются: автоматы не эквивалентны на данном слове."
    )
    return {
        "r1": {"states": r1["states"], "output_word": r1["output_word"]},
        "r2": {"states": r2["states"], "output_word": r2["output_word"]},
        "equal": equal,
        "note": note,
    }


def to_mealy(a: Automaton) -> Automaton:
    """Build the Mealy automaton equivalent to a Moore automaton (FA-06).

    ``P = Po, W = Wo, s0 = s0o, S = So, φ = φo``; the Mealy output on the
    transition ``(si, pj)`` equals the Moore output of the TARGET state:
    ``wk(t+1) = ψo(φo(si, pj))`` (methodic: vertex symbols are moved onto all
    arcs entering the vertex).
    """
    if a.kind != "moore" or a.psi is None:
        raise ValidationError([{"path": "input", "message": "нужен автомат Мура"}])
    psi_mealy: dict[tuple[str, str], str] = {
        (si, pj): a.psi[a.phi[(si, pj)]] for si in a.S for pj in a.P
    }
    return Automaton(
        P=a.P, S=a.S, s0=a.s0, phi=dict(a.phi), W=a.W, psi=psi_mealy, kind="mealy"
    )
