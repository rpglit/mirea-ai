"""Solver report contract (ARCH section 2.5, ADR-0008).

A solver turns task input data into a methodic-style report:
``Дано / Найти / Решение (шаги) / Ответ / Пояснения``. The report is a plain
JSON-serializable mapping with deterministic (sorted) key order so that
``GET /solve`` responses are reproducible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Step = dict[str, Any]  # {step: int, title: str, text: str, latex?: str, data?: Any}


@dataclass(frozen=True)
class Report:
    """A solver result in the «Дано/Найти/Решение/Ответ» shape.

    Example::

        Report(
            task_id="TASK-LSS-08",
            given={"ode": "y'(t) + 5y(t) = x(t)"},
            find=["передаточная функция Φ(s)"],
            solution=[{"step": 1, "title": "Показательное воздействие",
                       "text": "x(t) = e^{st}, y(t) = Φ(s)·e^{st}"}],
            answer={"phi_s": "1/(s + 5)"},
            notes=["система — апериодическое звено с T = 1/5, k = 1"],
        )
    """

    task_id: str
    given: dict[str, Any]
    find: list[str]
    solution: list[Step] = field(default_factory=list)
    answer: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-ready dict with deterministic key order."""
        return {
            "answer": _sorted(self.answer),
            "find": list(self.find),
            "given": _sorted(self.given),
            "notes": list(self.notes),
            "solution": sorted(self.solution, key=lambda s: s.get("step", 0)),
            "task_id": self.task_id,
        }


SolveFn = Callable[[dict[str, Any]], Report]


@dataclass(frozen=True)
class TaskInfo:
    """A catalog card of a solvable task (ADR-0010).

    ``group``: ``"PN" | "LSS" | "FA"``; ``type``: ``"задание" | "пример" | "зачёт"``;
    ``input_kind``: ``"net" | "lss" | "fa"`` (shape of the ``data`` argument,
    ARCH sections 4.1/4.2/4.3).
    """

    task_id: str
    group: str
    title: str
    source: str
    type: str
    input_kind: str
    fn: SolveFn


def _sorted(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: mapping[key] for key in sorted(mapping)}
