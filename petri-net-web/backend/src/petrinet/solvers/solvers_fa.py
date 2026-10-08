"""FA solvers: finite automata / F-schemes (ARCH section 2.5.3).

Covers TASK-FA-01..08: giving an automaton in the three methodic ways
(enumeration / table / graph), simulating a word by automaton ticks,
comparing Moore and Mealy on one word, and building the equivalent Mealy
automaton from a Moore one. Reports use the methodic glossary (section 5.3).
"""

from __future__ import annotations

from typing import Any

from petrinet.errors import ValidationError
from petrinet.solvers.automata import (
    compare,
    normalize,
    simulate,
    to_enumeration,
    to_graph,
    to_mealy,
    to_table,
)
from petrinet.solvers.report import Report, SolveFn, TaskInfo

_TASKS: dict[str, tuple[str, str, str]] = {
    "TASK-FA-01": (
        "Пример конечного автомата («чёрный ящик»)",
        "семинар 13, стр. 3–4",
        "пример",
    ),
    "TASK-FA-02": (
        "Автомат без выходного преобразователя (три способа задания)",
        "семинар 13, стр. 10–11",
        "пример",
    ),
    "TASK-FA-03": ("Пример автомата Мура", "семинар 13, стр. 17–19", "пример"),
    "TASK-FA-04": ("Пример автомата Мили", "семинар 14, стр. 3–5", "пример"),
    "TASK-FA-05": (
        "Сравнение работы автоматов Мура и Мили",
        "семинар 14, стр. 5",
        "пример",
    ),
    "TASK-FA-06": (
        "Эквивалентность: автомат Мура (рис. 1.10) → автомат Мили (рис. 1.11)",
        "семинар 14, стр. 6–8",
        "пример",
    ),
    "TASK-FA-07": (
        "Задание 1 (семинар 15): автомат Мура по таблице → перечисление и граф",
        "семинар 15, стр. 1",
        "задание",
    ),
    "TASK-FA-08": (
        "Задание 2 (семинар 15): автомат Мура по графу → перечисление и таблица",
        "семинар 15, стр. 2",
        "задание",
    ),
}



# --- built-in methodic automata (MATERIALS_ANALYSIS section 3.3) -------------

BLACK_BOX = {  # TASK-FA-01: one-state Mealy, p1->w1, p2->w2, p3->w2
    "P": ["p1", "p2", "p3"],
    "S": ["s0"],
    "s0": "s0",
    "type": "mealy",
    "W": ["w1", "w2"],
    "phi": [["s0", "p1", "s0"], ["s0", "p2", "s0"], ["s0", "p3", "s0"]],
    "psi": [["s0", "p1", "w1"], ["s0", "p2", "w2"], ["s0", "p3", "w2"]],
}

NO_OUTPUT = {  # TASK-FA-02
    "P": ["p1", "p2"],
    "S": ["s0", "s1", "s2"],
    "s0": "s0",
    "type": "none",
    "phi": [
        ["s0", "p1", "s0"],
        ["s0", "p2", "s1"],
        ["s1", "p1", "s1"],
        ["s1", "p2", "s2"],
        ["s2", "p1", "s2"],
        ["s2", "p2", "s0"],
    ],
}

MOORE = {  # TASK-FA-03 (table 1.5, graph 1.7)
    "P": ["p1", "p2"],
    "W": ["w0", "w1"],
    "S": ["s0", "s1", "s2", "s3"],
    "s0": "s0",
    "type": "moore",
    "phi": [
        ["s0", "p1", "s0"],
        ["s0", "p2", "s1"],
        ["s1", "p1", "s2"],
        ["s1", "p2", "s3"],
        ["s2", "p1", "s2"],
        ["s2", "p2", "s3"],
        ["s3", "p1", "s3"],
        ["s3", "p2", "s0"],
    ],
    "psi": {"s0": "w0", "s1": "w1", "s2": "w0", "s3": "w0"},
}

MEALY = {  # TASK-FA-04 (table 1.10)
    "P": ["p1", "p2"],
    "W": ["w0", "w1"],
    "S": ["s0", "s1", "s2"],
    "s0": "s0",
    "type": "mealy",
    "phi": [
        ["s0", "p1", "s0"],
        ["s0", "p2", "s1"],
        ["s1", "p1", "s1"],
        ["s1", "p2", "s2"],
        ["s2", "p1", "s2"],
        ["s2", "p2", "s0"],
    ],
    "psi": [
        ["s0", "p1", "w0"],
        ["s0", "p2", "w1"],
        ["s1", "p1", "w0"],
        ["s1", "p2", "w0"],
        ["s2", "p1", "w0"],
        ["s2", "p2", "w0"],
    ],
}

MOORE_110 = {  # TASK-FA-06: graph 1.10 (s0/*, s1/w2, s2/w1)
    "P": ["p1", "p2"],
    "W": ["*", "w1", "w2"],
    "S": ["s0", "s1", "s2"],
    "s0": "s0",
    "type": "moore",
    "phi": [
        ["s0", "p1", "s0"],
        ["s0", "p2", "s1"],
        ["s1", "p1", "s1"],
        ["s1", "p2", "s2"],
        ["s2", "p1", "s1"],
        ["s2", "p2", "s2"],
    ],
    "psi": {"s0": "*", "s1": "w2", "s2": "w1"},
}

MOORE_Z_TABLE = {  # TASK-FA-07 (A-22: states z0..z2, outputs y2/y1/y1)
    "P": ["x1", "x2"],
    "W": ["y1", "y2"],
    "S": ["z0", "z1", "z2"],
    "s0": "z0",
    "type": "moore",
    "phi": {
        "table": [
            ["z0", "z1", "z2"],
            ["z1", "z0", "z2"],
            ["z2", "z1", "z2"],
        ]
    },
    "psi": {"z0": "y2", "z1": "y1", "z2": "y1"},
}

MOORE_Z_GRAPH = {  # TASK-FA-08 (A-23)
    "P": ["x1", "x2"],
    "W": ["y1", "y2"],
    "S": ["Z0", "Z1", "Z2"],
    "s0": "Z0",
    "type": "moore",
    "phi": {
        "graph": {
            "nodes": [["Z0", "y1"], ["Z1", "y2"], ["Z2", "y1"]],
            "edges": [
                ["Z0", "x1", "Z2"],
                ["Z2", "x1", "Z0"],
                ["Z2", "x2", "Z2"],
                ["Z0", "x2", "Z1"],
                ["Z1", "x2", "Z0"],
                ["Z1", "x1", "Z2"],
            ],
        }
    },
    "psi": {"Z0": "y1", "Z1": "y2", "Z2": "y1"},
}

WORD = ["p1", "p2", "p2", "p1", "p2"]

FA_DEFAULTS: dict[str, dict[str, Any]] = {
    "TASK-FA-01": {"kind": "simulate", "input": BLACK_BOX, "word": ["p3", "p1", "p3", "p2"]},
    "TASK-FA-02": {"kind": "normalize", "input": NO_OUTPUT, "word": WORD},
    "TASK-FA-03": {"kind": "simulate", "input": MOORE, "word": WORD},
    "TASK-FA-04": {"kind": "simulate", "input": MEALY, "word": WORD},
    "TASK-FA-05": {"kind": "compare", "input": MOORE, "input2": MEALY, "word": WORD},
    "TASK-FA-06": {"kind": "to_mealy", "input": MOORE_110},
    "TASK-FA-07": {"kind": "normalize", "input": MOORE_Z_TABLE},
    "TASK-FA-08": {"kind": "normalize", "input": MOORE_Z_GRAPH},
}


def _find_for(task_id: str, spec: dict[str, Any]) -> list[str]:
    kind = spec.get("kind", "simulate")
    if kind == "normalize":
        if task_id == "TASK-FA-02":
            return [
                "задатель автомат перечислением, таблицей переходов и графом переходов",
                "моделирование работы автомата по переработке входного слова",
            ]
        if task_id == "TASK-FA-07":
            return ["описать автомат перечислением", "описать автомат графически"]
        return ["задатель автомат перечислением", "задатель автомат таблично"]
    if kind == "simulate":
        return ["как автомат перерабатывает входное слово (по автоматным тактам)"]
    if kind == "compare":
        return [
            "сравнить переработку одного входного слова обоими автоматами",
            "указать разницу в моменте считывания выходного символа",
        ]
    return [
        "построить автомат Мили, эквивалентный заданному автомату Мура "
        "(P = Po, W = Wo, s0 = s0o, S = So, φ = φo, wk(t+1) = ψ(si(t), pj(t)))"
    ]


def _given(spec: dict[str, Any]) -> dict[str, Any]:
    given: dict[str, Any] = {}
    for key in ("kind", "type", "word"):
        if key in spec:
            given[key] = spec[key]
    if "input" in spec:
        given["input"] = spec["input"]
        if "type" not in given and isinstance(spec["input"], dict):
            given["type"] = spec["input"].get("type", "none")
    if "input2" in spec:
        given["input2"] = spec["input2"]
    return given


def _ticks_text(r: dict[str, Any]) -> str:
    rows = [
        "  ".join(str(x) if x is not None else "—" for x in row) for row in r["ticks"]
    ]
    return "\n".join(rows)


def solve_fa(task_id: str, spec: dict[str, Any]) -> Report:
    """Solve one TASK-FA-NN (or a custom automaton task of the same shape).

    Example::

        solve_fa("TASK-FA-03", {"kind": "simulate", "type": "moore",
                                "input": {...автомат Мура...},
                                "word": ["p1", "p2", "p2", "p1", "p2"]})
    """
    spec = dict(spec or {})
    if task_id.startswith("custom:"):
        title, source, task_type = "пользовательское задание (автоматы)", "—", "задание"
    else:
        entry = _TASKS.get(task_id)
        if entry is None:
            from petrinet.errors import UnknownTaskError

            raise UnknownTaskError(task_id)
        title, source, task_type = entry
        merged = dict(FA_DEFAULTS[task_id])
        merged.update(spec)
        spec = merged
    kind = spec.get("kind")
    if kind not in ("normalize", "simulate", "compare", "to_mealy"):
        raise ValidationError(
            [{"path": "kind", "message": f"неизвестный вид задания: {kind}"}]
        )

    solution: list[dict[str, Any]] = []
    answer: dict[str, Any] = {}
    notes: list[str] = []
    automaton = normalize(spec["input"]) if "input" in spec else None

    if kind == "normalize" and automaton is not None:
        enum = to_enumeration(automaton)
        table = to_table(automaton)
        graph = to_graph(automaton)
        solution.append(
            {
                "step": 1,
                "title": "Перечисление",
                "text": "Функция перехода (и выхода) задана равенствами:",
                "data": {"enumeration": enum},
            }
        )
        if task_id in ("TASK-FA-02", "TASK-FA-08"):
            solution.append(
                {
                    "step": 2,
                    "title": "Таблица переходов",
                    "text": "Строки — состояния, столбцы — входные символы; "
                    "в ячейке — состояние, в которое переходит автомат.",
                    "data": table,
                }
            )
        if task_id in ("TASK-FA-02", "TASK-FA-07"):
            solution.append(
                {
                    "step": len(solution) + 1,
                    "title": "Граф переходов",
                    "text": "Вершины — состояния (Мура: si/wi), дуга si→sj "
                    "помечается входным символом pk (Мили: pk/wq).",
                    "data": graph,
                }
            )
        answer = {"enumeration": enum}
        if task_id in ("TASK-FA-02", "TASK-FA-08"):
            answer["table"] = table
        if task_id in ("TASK-FA-02", "TASK-FA-07"):
            answer["graph"] = graph
        if "word" in spec and spec["word"]:
            r = simulate(automaton, spec["word"])
            solution.append(
                {
                    "step": len(solution) + 1,
                    "title": "Моделирование входного слова",
                    "text": _ticks_text(r)
                    + f"\nПоследовательность состояний: {' → '.join(r['states'])}."
                    + (
                        f" Выходное слово: {''.join(r['output_word'])}."
                        if r["output_word"]
                        else ""
                    ),
                    "data": {"ticks": r["ticks"], "states": r["states"]},
                }
            )
            answer["states"] = r["states"]
            if r["output_word"]:
                answer["output_word"] = r["output_word"]
            if automaton.kind == "moore":
                notes.append(
                    "Значение выхода в такт t0 (w*) не учитывается: оно определяется "
                    "начальным состоянием автомата Мура до подачи первого входного "
                    "символа и не входит в выходное слово."
                )

    elif kind == "simulate" and automaton is not None:
        r = simulate(automaton, spec.get("word", []))
        text = _ticks_text(r) + "\nПоследовательность состояний: " + " → ".join(r["states"])
        if r["output_word"]:
            text += f". Выходное слово: {''.join(r['output_word'])}."
        solution.append(
            {"step": 1, "title": "Моделирование по автоматным тактам", "text": text,
             "data": {"ticks": r["ticks"]}}
        )
        answer = {"states": r["states"]}
        if r["output_word"]:
            answer["output_word"] = r["output_word"]
        answer["graph"] = to_graph(automaton)
        if automaton.kind == "moore":
            notes.append(
                "w* в t0 не входит в выходное слово (определяется начальным состоянием)."
            )
        elif automaton.kind == "mealy":
            notes.append(
                "В автомате Мили в t0 выхода нет: первый выходной символ "
                "появляется после подачи первого входного символа."
            )

    elif kind == "compare":
        a1 = normalize(spec["input"])
        a2 = normalize(spec["input2"])
        word = spec.get("word", [])
        cmp = compare(a1, a2, word)
        solution.append(
            {
                "step": 1,
                "title": "Переработка слова обоими автоматами",
                "text": f"Автомат 1: {''.join(cmp['r1']['output_word']) or '—'}; "
                f"автомат 2: {''.join(cmp['r2']['output_word']) or '—'}. {cmp['note']}",
                "data": {"r1": cmp["r1"], "r2": cmp["r2"]},
            }
        )
        cmp["r1"]["graph"] = to_graph(a1)
        cmp["r2"]["graph"] = to_graph(a2)
        answer = {"r1": cmp["r1"], "r2": cmp["r2"], "equal": cmp["equal"]}

    elif kind == "to_mealy" and automaton is not None:
        mealy = to_mealy(automaton)
        answer = {
            "mealy": {
                "enumeration": to_enumeration(mealy),
                "table": to_table(mealy),
                "graph": to_graph(mealy),
            }
        }
        solution.append(
            {
                "step": 1,
                "title": "Конструкция эквивалентного автомата Мили",
                "text": "P = Po, W = Wo, s0 = s0o, S = So, φ(si, pj) = φo(si, pj); "
                "выход автомата Мили на переходе в новое состояние равен выходу "
                "автомата Мура этого нового состояния: wk(t+1) = ψo(φo(si(t), pj(t))).",
            }
        )
        solution.append(
            {
                "step": 2,
                "title": "Графический метод",
                "text": "Выходные символы, которыми помечены вершины графа автомата "
                "Мура, перенесены на все дуги, входящие в каждую вершину.",
                "data": {"graph": to_graph(mealy)},
            }
        )
        notes.append(
            "Эквивалентность: любое входное слово оба автомата перерабатывают в "
            "совпадающие выходные слова (при обоих в начальном состоянии)."
        )

    return Report(
        task_id=task_id,
        given=_given(spec),
        find=_find_for(task_id, spec),
        solution=solution,
        answer=answer,
        notes=notes,
    )


def _make_fn(task_id: str) -> SolveFn:
    def fn(spec: dict[str, Any]) -> Report:
        return solve_fa(task_id, spec)

    return fn


REGISTRY: list[TaskInfo] = [
    TaskInfo(
        task_id=task_id,
        group="FA",
        title=title,
        source=source,
        type=task_type,
        input_kind="fa",
        fn=_make_fn(task_id),
    )
    for task_id, (title, source, task_type) in _TASKS.items()
]
