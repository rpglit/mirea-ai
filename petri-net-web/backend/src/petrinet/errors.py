"""Typed application errors for the Petri net domain (see ADR-0006)."""

from __future__ import annotations


class PetriNetError(Exception):
    """Base class for all typed application errors."""


class ParseError(PetriNetError):
    """Malformed net text. Example: ParseError(12, 'expected a place name')."""

    position: int
    message: str

    def __init__(self, position: int, message: str) -> None:
        self.position = position
        self.message = message

    def __str__(self) -> str:
        return f"parse error at position {self.position}: {self.message}"


class ValidationError(PetriNetError):
    """Schema violations. Example: ValidationError([{'path': 'p1', 'message': 'bad'}])."""

    problems: list[dict[str, str]]

    def __init__(self, problems: list[dict[str, str]]) -> None:
        self.problems = problems

    def __str__(self) -> str:
        return f"validation failed ({len(self.problems)} problems)"


class UnknownSessionError(PetriNetError):
    """Session id not found. Example: UnknownSessionError('a3f2c81d')."""

    session_id: str

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    def __str__(self) -> str:
        return f"unknown session: {self.session_id}"


class CapExceededError(PetriNetError):
    """Reachability cap exceeded. Example: CapExceededError(50000)."""

    limit: int

    def __init__(self, limit: int) -> None:
        self.limit = limit

    def __str__(self) -> str:
        return f"reachability cap exceeded: more than {self.limit} markings"


class ConflictError(PetriNetError):
    """Parallel firing is impossible: a disabled transition or a conflict.

    ``transitions`` of length 1 — that transition is not enabled at the
    marking; a pair — they conflict (share the input place ``place``).
    Example: ConflictError(("t1", "t2"), "p1").
    """

    transitions: tuple[str, ...]
    place: str | None

    def __init__(self, transitions: tuple[str, ...], place: str | None = None) -> None:
        self.transitions = transitions
        self.place = place

    def __str__(self) -> str:
        if len(self.transitions) == 1:
            return f"конфликт: переход '{self.transitions[0]}' не разрешён в данной маркировке"
        names = " и ".join(f"'{t}'" for t in self.transitions)
        if self.place is None:
            return f"конфликт: переходы {names} не могут сработать одновременно"
        return f"конфликт: переходы {names} имеют общую входную позицию '{self.place}'"


class UnsupportedModelError(PetriNetError):
    """The net model is not supported by this analysis (delays / colors).

    Example: UnsupportedModelError('delays').
    """

    feature: str

    def __init__(self, feature: str) -> None:
        self.feature = feature

    def __str__(self) -> str:
        if self.feature == "delays":
            return (
                "граф достижимости не поддерживается для временных сетей "
                "(задержки τ) — используйте пошаговую симуляцию решателя"
            )
        return (
            "граф достижимости не поддерживается для цветных сетей — "
            "используйте пошаговую симуляцию решателя"
        )


class TransitionNotEnabledError(PetriNetError):
    """Not enabled at marking. Example: TransitionNotEnabledError((1, 0), 't4')."""

    marking: tuple[int, ...]
    transition: str

    def __init__(self, marking: tuple[int, ...], transition: str) -> None:
        self.marking = marking
        self.transition = transition

    def __str__(self) -> str:
        return f"transition '{self.transition}' is not enabled at marking {self.marking}"
