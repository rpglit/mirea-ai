"""Extended PN solvers (ARCH section 2.5.1, groups M8-M12).

Priorities (PN-10, PN-30): conflict resolution by Pr t via core.active.
Temporal nets (PN-15, PN-32): discrete tick simulation with arc delays
tau (default 1), tokens in flight arrive at t_fire + tau.
Inhibitor nets (PN-33): scenarios with explicit inhibitor status.
Colored nets (PN-36, PN-37): simulation of values and guards (A-21:
simulation only, no reachability graphs).
"""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from typing import Any

from petrinet.core import PetriNet, fire
from petrinet.errors import UnknownTaskError, ValidationError
from petrinet.parser import parse_json
from petrinet.solvers.report import Report, SolveFn, TaskInfo

MAX_STEPS_LIMIT = 1000
DEFAULT_HORIZON = 20

_CUSTOM_FIND: dict[str, list[str]] = {
    "priority": ["активные переходы с учётом Pr t, конфликты, результирующие маркировки"],
    "temporal": ["симуляция по тактам: маркировки, срабатывания, период цикла"],
    "inhibitor": ["статус ингибиторов по сценариям, срабатывания, итоговые маркировки"],
    "colored": ["симуляция значений и гвардов (только симуляция, A-21)"],
}


def _analytic(net: PetriNet) -> dict[str, Any]:
    return {
        "P": list(net.places),
        "T": list(net.transitions),
        "I": {
            t: [[p, w] for p, w in arcs]
            for t, arcs in zip(net.transitions, net.inputs, strict=True)
        },
        "O": {
            t: [[p, w] for p, w in arcs]
            for t, arcs in zip(net.transitions, net.outputs, strict=True)
        },
        "mu": list(net.initial_marking),
        "inhibitors": (
            {t: list(p) for t, p in zip(net.transitions, net.inhibitors, strict=True)}
            if net.inhibitors is not None
            else None
        ),
        "priorities": (
            {t: pr for t, pr in zip(net.transitions, net.priorities, strict=True)}
            if net.priorities is not None
            else None
        ),
        "delays": (
            {
                t: [[p, tau] for p, tau in arcs]
                for t, arcs in zip(net.transitions, net.delays, strict=True)
                if arcs
            }
            if net.delays is not None
            else None
        ),
    }


def _graph(net: PetriNet) -> dict[str, Any]:
    m = net.initial_marking
    arcs: list[list[Any]] = []
    for i, t in enumerate(net.transitions):
        for p, w in net.inputs[i]:
            arcs.append([p, t, w])
        for p, w in net.outputs[i]:
            arcs.append([t, p, w])
    return {
        "places": [[p, m[i]] for i, p in enumerate(net.places)],
        "transitions": list(net.transitions),
        "arcs": arcs,
    }


def _remarked(net: PetriNet, m: tuple[int, ...]) -> PetriNet:
    payload: dict[str, object] = {
        "places": list(net.places),
        "transitions": list(net.transitions),
        "inputs": {
            t: {p: w for p, w in arcs}
            for t, arcs in zip(net.transitions, net.inputs, strict=True)
        },
        "outputs": {
            t: {p: w for p, w in arcs}
            for t, arcs in zip(net.transitions, net.outputs, strict=True)
        },
        "initial_marking": {p: x for p, x in zip(net.places, m, strict=True)},
    }
    if net.priorities is not None:
        payload["priorities"] = {
            t: pr for t, pr in zip(net.transitions, net.priorities, strict=True)
        }
    return parse_json(payload)


# --- priorities (M8) ----------------------------------------------------------


def _active_report(net: PetriNet, m: tuple[int, ...]) -> dict[str, Any]:
    """Enabled set, priority-active set, and the exclusion reasons."""
    priorities = net.priorities
    enabled = [t for t in net.transitions if net.enabled(m, t)]
    active = list(net.active(m)) if priorities is not None else list(enabled)
    excluded: list[dict[str, Any]] = []
    if priorities is not None:
        inputs_of = {
            t: {p for p, _ in arcs}
            for t, arcs in zip(net.transitions, net.inputs, strict=True)
        }
        for t in enabled:
            if t in active:
                continue
            ti = net.transitions.index(t)
            beaters = [
                o
                for o in enabled
                if o != t
                and priorities[net.transitions.index(o)] > priorities[ti]
                and inputs_of[o] & inputs_of[t]
            ]
            excluded.append(
                {
                    "t": t,
                    "reason": "конфликт за общий вход: "
                    + ", ".join(
                        f"{b} (Pr {priorities[net.transitions.index(b)]} "
                        f"> Pr {priorities[ti]})"
                        for b in beaters
                    ),
                }
            )
    return {"enabled": enabled, "active": active, "excluded": excluded}


def g_priority(
    task: dict[str, Any] | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    steps: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = [n for n in opts.get("notes", []) if n]
    scenarios = list(opts.get("scenarios", []))
    results = []
    for sc in scenarios:
        n = parse_json(sc["net"]) if "net" in sc else net
        m0 = tuple(sc.get("marking", n.initial_marking))
        sigma = list(sc.get("sequence", []))
        trace = []
        m = m0
        blocked_at: int | None = None
        for pos, t in enumerate(sigma, start=1):
            rep = _active_report(n, m)
            entry: dict[str, Any] = {
                "marking": list(m),
                "enabled": rep["enabled"],
                "active": rep["active"],
                "excluded": rep["excluded"],
            }
            if t not in rep["active"]:
                blocked_at = pos
                entry["fired"] = None
                entry["note"] = f"{t} не в активном множестве (приоритет) или не разрешён"
                trace.append(entry)
                break
            m = fire(n, m, t)
            entry["fired"] = t
            entry["to"] = list(m)
            trace.append(entry)
        results.append(
            {
                "name": sc["name"],
                "trace": trace,
                "final": list(m) if blocked_at is None else None,
                "blocked_at": blocked_at,
            }
        )
    answer["scenarios"] = results
    steps.append(
        {
            "step": 1,
            "title": "Срабатывания с учётом приоритетов (M8)",
            "text": (
                "Если разрешённые переходы конфликтуют за общий вход, срабатывает "
                "переход с наибольшим приоритетом Pr t (конфликт — общий вход, "
                "глоссарий §5.1)."
            ),
            "data": {"scenarios": results},
        }
    )
    return steps, answer, notes


# --- temporal nets (M9) ---------------------------------------------------------


def _tau(net: PetriNet, ti: int, place: str) -> int:
    if net.delays is None:
        return 1
    for p, tau in net.delays[ti]:
        if p == place:
            return tau
    return 1


def g_temporal(
    task: dict[str, Any] | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    horizon = int(opts.get("horizon", DEFAULT_HORIZON))
    if not 1 <= horizon <= max_steps:
        raise ValidationError([{"path": "horizon", "message": "горизонт вне диапазона"}])
    idx = {p: i for i, p in enumerate(net.places)}
    m = list(net.initial_marking)
    in_flight: list[list[Any]] = []  # [arrive_tick, place, weight]
    ticks: list[dict[str, Any]] = []
    fired_log: list[list[str]] = []
    t = 0
    done = False
    while t < horizon and not done:
        for at, p, w in list(in_flight):
            if at == t:
                m[idx[p]] += w
                in_flight.remove([at, p, w])
        fired: list[str] = []
        next_m = list(m)
        for i, tr in enumerate(net.transitions):
            if net.enabled(tuple(m), tr):
                fired.append(tr)
                for p, w in net.inputs[i]:
                    next_m[idx[p]] -= w
                for p, w in net.outputs[i]:
                    in_flight.append([t + _tau(net, i, p), p, w])
        m = next_m
        ticks.append(
            {
                "tick": t,
                "marking": list(m),
                "fired": fired,
                "in_flight": [[p, at - t, w] for at, p, w in sorted(in_flight)],
            }
        )
        fired_log.append(fired)
        if not fired and not in_flight:
            done = True
        t += 1
    period: int | None = None
    for p in range(1, len(fired_log) // 2 + 1):
        if fired_log[:p] * 2 == fired_log[: 2 * p]:
            period = p
            break
    steps = [
        {
            "step": 1,
            "title": "Дискретная симуляция по тактам (M9)",
            "text": (
                "τ на выходных дугах (по умолчанию 1): метка, посланная в такт t, "
                f"появляется в позиции в такт t+τ. Горизонт: {horizon} тактов."
            ),
            "data": {"ticks": ticks, "period": period},
        }
    ]
    answer = {"ticks": ticks, "period": period}
    notes = [n for n in opts.get("notes", []) if n]
    if period is not None:
        notes.append(f"период цикла — {period} тактов")
    return steps, answer, notes


# --- inhibitors (M2 with ⊣) ------------------------------------------------------


def g_inhibitor(
    task: dict[str, Any] | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    steps: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = [n for n in opts.get("notes", []) if n]
    idx = {p: i for i, p in enumerate(net.places)}
    scenarios = list(opts.get("scenarios", []))
    results = []
    for sc in scenarios:
        n = parse_json(sc["net"]) if "net" in sc else net
        m0 = tuple(sc.get("marking", n.initial_marking))
        sigma = list(sc.get("sequence", []))
        trace = []
        m = m0
        for t in sigma:
            ti = n.transitions.index(t)
            inputs_ok = n.enabled(m, t) if n.inhibitors is None else _inputs_ok(n, m, ti)
            blocked_by = (
                [p for p in n.inhibitors[ti] if m[idx[p]] != 0]
                if n.inhibitors is not None
                else []
            )
            enabled = inputs_ok and not blocked_by
            entry: dict[str, Any] = {
                "t": t,
                "marking": list(m),
                "inputs_ok": inputs_ok,
                "inhibitor_blocked": blocked_by,
                "enabled": enabled,
            }
            if enabled:
                m = fire(n, m, t)
                entry["to"] = list(m)
            trace.append(entry)
        results.append(
            {
                "name": sc["name"],
                "before": list(m0),
                "trace": trace,
                "after": list(m),
                "text": sc.get("text", ""),
            }
        )
    answer["scenarios"] = results
    steps.append(
        {
            "step": 1,
            "title": "Сценарии с ингибиторными дугами (⊣)",
            "text": (
                "Ингибиторная дуга p ⊣ t (вес 1): если в p хотя бы одна метка, "
                "t заблокирован, даже если обычные входы удовлетворены."
            ),
            "data": {"scenarios": results},
        }
    )
    return steps, answer, notes


def _inputs_ok(net: PetriNet, m: tuple[int, ...], ti: int) -> bool:
    idx = {p: i for i, p in enumerate(net.places)}
    return all(m[idx[p]] >= w for p, w in net.inputs[ti])


# --- colored nets (M12, A-21: simulation only) ----------------------------------

_GUARD_OPS: dict[type, Callable[[int | float, int | float], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_BIN_OPS: dict[type, Callable[[int | float, int | float], int | float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}


def _eval_expr(expr: str, values: dict[str, float]) -> bool | float:
    """Safely evaluate a methodic guard/expression (ast only, no eval)."""
    text = expr.replace("×", "*").replace("·", "*").replace("−", "-")
    text = re.sub(r"(?<![=!<>])=(?!=)", "==", text)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValidationError(
            [{"path": "expressions", "message": f"некорректное выражение: {expr}"}]
        ) from exc

    def ev(node: ast.AST) -> int | float | bool:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in values:
                raise ValidationError(
                    [
                        {
                            "path": "expressions",
                            "message": f"не задано значение: {node.id}",
                        }
                    ]
                )
            return values[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            return _GUARD_OPS[type(node.ops[0])](ev(node.left), ev(node.comparators[0]))
        raise ValidationError(
            [{"path": "expressions", "message": f"неподдерживаемый оператор в: {expr}"}]
        )

    return ev(tree)


def g_colored(
    task: dict[str, Any] | None, net: PetriNet | None, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    steps: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = [n for n in opts.get("notes", []) if n]
    if "expressions" in opts:
        values = dict(opts.get("values", {}))
        evaluated = []
        for expr in opts["expressions"]:
            kind = (
                "guard"
                if re.search(r"(?<![=!<>])([=<>]|==)", expr.replace("−", "-"))
                else "output"
            )
            result = _eval_expr(expr, values)
            evaluated.append(
                {
                    "expr": expr,
                    "kind": kind,
                    "value": bool(result) if kind == "guard" else result,
                }
            )
        answer["evaluated"] = evaluated
        steps.append(
            {
                "step": 1,
                "title": "Выражения гвардов и значений меток (M12)",
                "text": (
                    "Гвард — предикат на значениях меток (вход), выражение значения "
                    f"— вычисляется при выпуске метки. Значения для демонстрации: {values}."
                ),
                "data": {"values": values, "evaluated": evaluated},
            }
        )
    else:
        if net is None:
            raise ValidationError(
                [{"path": "net", "message": "для симуляции цветной сети нужен JSON сети"}]
            )
        sigma = list(opts["sigma"])
        trace = []
        m = net.initial_marking
        for t in sigma:
            m = fire(net, m, t)
            trace.append(
                {
                    "t": t,
                    "marking": list(m),
                    "colors": opts.get("color_notes", {}).get(t, ""),
                }
            )
        answer["trace"] = trace
        steps.append(
            {
                "step": 1,
                "title": "Пошаговая симуляция цветной сети (M12)",
                "text": (
                    "Цвет — значение метки (свойства объекта); смена цвета описывается "
                    "в примечаниях шагов. Классификация и графы достижимости для "
                    "цветных сетей не вычисляются (A-21: только симуляция)."
                ),
                "data": {"trace": trace},
            }
        )
    return steps, answer, notes


# --- built-in nets and tasks ------------------------------------------------------

_pn10 = {
    "places": ["r1", "r2", "f", "w", "w2", "d"],
    "transitions": ["t1", "t2", "t3", "t4"],
    "inputs": {
        "t1": {"r1": 1},
        "t2": {"r2": 1},
        "t3": {"f": 1, "w": 1},
        "t4": {"w2": 1},
    },
    "outputs": {
        "t1": {"w": 1},
        "t2": {"w": 1},
        "t3": {"w2": 1},
        "t4": {"f": 1, "d": 1},
    },
    "initial_marking": {"r1": 1, "r2": 1, "f": 2, "w": 0, "w2": 0, "d": 0},
    "priorities": {"t1": 0, "t2": 0, "t3": 1, "t4": 0},
}

_pn30 = {
    "places": ["p1", "p2", "p3", "p4"],
    "transitions": ["t1", "t2"],
    "inputs": {"t1": {"p1": 1, "p2": 1}, "t2": {"p2": 1}},
    "outputs": {"t1": {"p3": 1}, "t2": {"p4": 1}},
    "initial_marking": {"p1": 0, "p2": 0, "p3": 0, "p4": 0},
    "priorities": {"t1": 1, "t2": 0},
}

_pn15 = {
    "places": ["a", "b", "c", "d", "e"],
    "transitions": ["t1", "t2", "t3", "t4", "t5"],
    "inputs": {
        "t1": {"a": 1},
        "t2": {"b": 1},
        "t3": {"c": 1},
        "t4": {"d": 1},
        "t5": {"e": 1},
    },
    "outputs": {
        "t1": {"b": 1},
        "t2": {"c": 1},
        "t3": {"d": 1},
        "t4": {"e": 1},
        "t5": {"a": 1},
    },
    "initial_marking": {"a": 1, "b": 0, "c": 0, "d": 0, "e": 0},
    "delays": {"t1": {"b": 3}, "t2": {"c": 1}, "t3": {"d": 1}, "t4": {"e": 3}, "t5": {"a": 1}},
}

_pn32 = {
    "places": ["g", "y", "r"],
    "transitions": ["t1", "t2", "t3"],
    "inputs": {"t1": {"g": 1}, "t2": {"y": 1}, "t3": {"r": 1}},
    "outputs": {"t1": {"y": 1}, "t2": {"r": 1}, "t3": {"g": 1}},
    "initial_marking": {"g": 0, "y": 1, "r": 0},
    "delays": {"t2": {"r": 4}, "t3": {"g": 3}},
}

_pn33 = {
    "places": ["a", "i", "k", "l"],
    "transitions": ["t1", "t2"],
    "inputs": {"t1": {"a": 1, "i": 1}, "t2": {"i": 1}},
    "outputs": {"t1": {"k": 1}, "t2": {"l": 1}},
    "initial_marking": {"a": 0, "i": 0, "k": 0, "l": 0},
    "inhibitors": {"t2": ["a"]},
}

_pn37 = {
    "places": ["grains", "sugar", "water_cold", "water_hot", "ground", "money", "coffee"],
    "transitions": ["t1", "t2"],
    "inputs": {
        "t1": {"grains": 1, "water_cold": 1},
        "t2": {"ground": 1, "water_hot": 1, "sugar": 1, "money": 1},
    },
    "outputs": {
        "t1": {"ground": 1, "water_hot": 1},
        "t2": {"coffee": 1},
    },
    "initial_marking": {
        "grains": 1,
        "sugar": 1,
        "water_cold": 1,
        "water_hot": 0,
        "ground": 0,
        "money": 1,
        "coffee": 0,
    },
}


TASKS: dict[str, Any] = {
    "TASK-PN-10": {
        "title": "Сервер БД: ≤2 запросов параллельно, приоритеты",
        "source": "семинар 3, стр. 9, Задание 1",
        "type": "задание",
        "statement": (
            "Сервер обрабатывает одновременно не более двух запросов; ждёт запросы "
            "программистов, обрабатывает их и отправляет результат. Указать приоритет."
        ),
        "find": ("граф с приоритетами Pr t", "демонстрация: два запроса обработаны"),
        "groups": ("model", "priority"),
        "net": _pn10,
        "options": {
            "notes": [
                "f = 2 метки: не более двух запросов в обработке (w + w2 ≤ 2);",
                "приоритет: у t3 (начало обработки) Pr = 1, у остальных Pr = 0 (по указанию);",
                "решение — модель: в методичке сеть не задана численно.",
            ],
            "scenarios": [
                {
                    "name": "два запроса от двух программистов",
                    "sequence": ["t1", "t3", "t2", "t3", "t4", "t4"],
                }
            ],
        },
    },
    "TASK-PN-30": {
        "title": "Пример 1 (семинар 3): сеть с приоритетами",
        "source": "семинар 3, стр. 3",
        "type": "пример",
        "statement": (
            "P = {p1..p4}, T = {t1, t2}; дуги p1→t1, p2→t1, p2→t2, t1→p3, t2→p4; "
            "Pr(t1) = 1, Pr(t2) = 0. Сценарий a): p1=3, p2=1; сценарий b): p1=0, p2=1."
        ),
        "find": (
            "конфликт за p2 и его разрешение по приоритету",
            "результирующие маркировки для обоих сценариев",
        ),
        "groups": ("priority",),
        "net": _pn30,
        "options": {
            "scenarios": [
                {
                    "name": "a) p1=3, p2=1: конфликт",
                    "marking": [3, 1, 0, 0],
                    "sequence": ["t1"],
                },
                {
                    "name": "b) p1=0, p2=1: конфликта нет",
                    "marking": [0, 1, 0, 0],
                    "sequence": ["t2"],
                },
            ],
        },
    },
    "TASK-PN-15": {
        "title": "Два светофора с тактами 5/3/1",
        "source": "семинар 4, стр. 1, Задание 4",
        "type": "задание",
        "statement": (
            "Два согласованных светофора: красный 5 тактов, зелёный 3, жёлтый 1; "
            "зелёный на одном ⇔ красный на другом."
        ),
        "find": ("граф (фазы)", "симуляция по тактам: цикл 9 тактов"),
        "groups": ("model", "temporal"),
        "net": _pn15,
        "options": {
            "notes": [
                "фазы: a = (зелёный 1, красный 2) — 3 такта; b = (жёлтый 1, красный 2) — 1 такт; "
                "c = (оба красные) — 1 такт; d = (красный 1, зелёный 2) — 3 такта; "
                "e = (красный 1, жёлтый 2) — 1 такт;",
                "красный 1 = c+d+e = 1+3+1 = 5 тактов; зелёный = 3; жёлтый = 1;",
                "решение — модель: длительности фаз — задержки τ временной сети.",
            ],
        },
    },
    "TASK-PN-32": {
        "title": "Пример 3 (семинар 3): светофор, временная сеть (τ = 4 и 3)",
        "source": "семинар 3, стр. 5",
        "type": "пример",
        "statement": (
            "Светофор: цикл красный→зелёный→жёлтый; метка в «жёлтый»; задержки: 4 "
            "(в «красный») и 3 (в «зелёный»), остальные дуги — τ = 1."
        ),
        "find": ("симуляция по тактам с задержками τ", "период цикла"),
        "groups": ("temporal",),
        "net": _pn32,
        "options": {},
    },
    "TASK-PN-33": {
        "title": "Ингибиторная сеть: команда i : Dec a, k, l",
        "source": "семинар 3, стр. 6",
        "type": "пример",
        "statement": (
            "P = {a, i, k, l}, T = {t1, t2}; дуги a→t1, i→t1, t1→k, i→t2, t2→l; "
            "ингибиторная дуга a ⊣ t2. Сценарий 1: a=3; сценарий 2: a=0."
        ),
        "find": (
            "сценарий a≥1: t1 (Dec a; k++)",
            "сценарий a=0: t2 (ветвление на l)",
            "реализация if a≠0 then a:=a−1; goto k else goto l",
        ),
        "groups": ("inhibitor",),
        "net": _pn33,
        "options": {
            "scenarios": [
                {
                    "name": "a = 3 (a ≥ 1)",
                    "marking": [3, 1, 0, 0],
                    "sequence": ["t1"],
                    "text": "t1 разрешён (a≥1, i=1); t2 заблокирован ингибитором a⊣t2 (a=3).",
                },
                {
                    "name": "a = 0",
                    "marking": [0, 1, 0, 0],
                    "sequence": ["t2"],
                    "text": "t1 не разрешён (a=0); t2 разрешён (ингибитор анулирован).",
                },
            ],
        },
    },
    "TASK-PN-36": {
        "title": "Цветная сеть Петри с гвардами (иллюстративная)",
        "source": "семинар 5, стр. 4",
        "type": "пример",
        "statement": (
            "Позиции a, b, c, n, f; начальные метки n=3, c=1; выражения «a−1», "
            "«a>1», «b=1», «b>1», «b×c»."
        ),
        "find": ("гварды как предикаты на значениях меток", "выражения значений выпускаемых меток"),
        "groups": ("colored",),
        "net": None,
        "options": {
            "expressions": ["a-1", "a>1", "b=1", "b>1", "b×c"],
            "values": {"a": 2, "b": 1, "c": 3},
            "notes": [
                "иллюстративный пример методички (рисунок): полная сеть численно не задана;",
                "значения a=2, b=1, c=3 — демонстрационные (н = 3, c = 1 из условия);",
                "«a−1» и «b×c» — выражения значений меток (не предикаты);",
            ],
        },
    },
    "TASK-PN-37": {
        "title": "Цветная сеть: кофеварка (2 шага)",
        "source": "семинар 5, стр. 5–6",
        "type": "пример",
        "statement": (
            "Модель кофеварки: Зёрна кофе, Сахар, Вода, Заказ (деньги) → Готовый кофе. "
            "Шаг 1: перемолка зёрен и нагрев воды. Шаг 2: варка кофе."
        ),
        "find": ("2 шага с изменением свойств объектов", "готовый кофе"),
        "groups": ("colored",),
        "net": _pn37,
        "options": {
            "sigma": ["t1", "t2"],
            "color_notes": {
                "t1": "Вода: холодная → горячая; Зёрна: зёрна → молотые зёрна",
                "t2": "Молотые зёрна + горячая вода + сахар + деньги → готовый кофе",
            },
            "notes": [
                "цвет метки = свойства объекта (температура воды, форма зёрен);",
                "сетевая динамика — как в простых сетях Петри (слайд методички).",
            ],
        },
    },
}


def _model(
    task: dict[str, Any] | None, net: PetriNet, opts: dict[str, Any], max_steps: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    answer: dict[str, Any] = {"analytic": _analytic(net)}
    graph = _graph(net)
    answer["graph"] = graph
    steps = [
        {
            "step": 1,
            "title": "Аналитическое описание",
            "text": "S = (P, T, I, O, µ); dуги — с весами (и ⊣/Pr/τ, если заданы).",
            "data": answer["analytic"],
        },
        {
            "step": 2,
            "title": "Граф сети",
            "text": "Круги — позиции, прямоугольники — переходы, дуги с весами.",
            "data": graph,
        },
    ]
    invariants: list[str] = [str(n) for n in opts.get("notes", []) if n]
    if invariants:
        steps.append(
            {
                "step": 3,
                "title": "Смысловые инварианты",
                "text": "",
                "data": {"invariants": invariants},
            }
        )
        answer["invariants"] = invariants
    return steps, answer, []




GROUP_FNS: dict[str, Callable[..., tuple[list[dict[str, Any]], dict[str, Any], list[str]]]] = {
    "model": _model,
    "priority": g_priority,
    "temporal": g_temporal,
    "inhibitor": g_inhibitor,
    "colored": g_colored,
}


def solve_pn_ext(task_id: str, spec: dict[str, Any] | None = None) -> Report:
    """Solve one extended-model TASK-PN-NN (or a custom task of the same shape)."""
    spec = spec or {}
    max_steps = int(spec.get("max_steps", 100))
    if not 1 <= max_steps <= MAX_STEPS_LIMIT:
        raise ValidationError(
            [{"path": "max_steps", "message": f"нужно целое число 1..{MAX_STEPS_LIMIT}"}]
        )
    if task_id.startswith("custom:"):
        group_name = task_id.split(":", 1)[1]
        if group_name not in GROUP_FNS or group_name == "model":
            raise ValidationError(
                [{"path": "task_id", "message": f"неизвестная группа: {group_name}"}]
            )
        task: dict[str, Any] | None = None
        groups: tuple[str, ...] = (group_name,)
        if group_name == "colored" and "expressions" in spec:
            payload: dict[str, Any] | None = None
        else:
            if not isinstance(spec.get("net"), dict):
                raise ValidationError([{"path": "net", "message": "нужен JSON сети (net)"}])
            payload = spec["net"]
    else:
        task = TASKS.get(task_id)
        if task is None:
            raise UnknownTaskError(task_id)
        groups = tuple(task["groups"])
        payload = spec.get("net") or task["net"]
        merged_opts = dict(task["options"])
        if payload is None and not (
            set(groups) <= {"colored"} and "expressions" in merged_opts
        ):
            raise ValidationError(
                    [
                        {
                            "path": "net",
                            "message": f"для {task_id} нет встроенной сети — передайте net",
                        }
                    ]
                )
    net = parse_json(payload) if payload is not None else None

    opts: dict[str, Any] = dict(task["options"] if task else {})
    for key in (
        "sequence",
        "marking",
        "horizon",
        "sigma",
        "expressions",
        "values",
        "scenarios",
    ):
        if key in spec:
            opts[key] = spec[key]

    steps: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = []
    for gname in groups:
        if gname == "model" and net is None:
            continue
        g_steps, g_answer, g_notes = GROUP_FNS[gname](task, net, opts, max_steps)
        steps.extend(g_steps)
        answer.update(g_answer)
        notes.extend(g_notes)
    for i, st in enumerate(steps, start=1):
        st["step"] = i

    given: dict[str, Any] = {}
    if task:
        given["statement"] = task["statement"]
    if payload is not None:
        given["net"] = payload
    find = list(task["find"]) if task else list(_CUSTOM_FIND[groups[0]])

    return Report(
        task_id=task_id,
        given=given,
        find=list(find),
        solution=steps,
        answer=answer,
        notes=notes,
    )


def _make_fn(task_id: str) -> SolveFn:
    def fn(spec: dict[str, Any]) -> Report:
        return solve_pn_ext(task_id, spec)

    return fn


REGISTRY: list[TaskInfo] = [
    TaskInfo(
        task_id=task_id,
        group="PN",
        title=t["title"],
        source=t["source"],
        type=t["type"],
        input_kind="pn",
        fn=_make_fn(task_id),
    )
    for task_id, t in TASKS.items()
]
