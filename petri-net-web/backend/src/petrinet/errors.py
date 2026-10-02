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


class TransitionNotEnabledError(PetriNetError):
    """Not enabled at marking. Example: TransitionNotEnabledError((1, 0), 't4')."""

    marking: tuple[int, ...]
    transition: str

    def __init__(self, marking: tuple[int, ...], transition: str) -> None:
        self.marking = marking
        self.transition = transition

    def __str__(self) -> str:
        return f"transition '{self.transition}' is not enabled at marking {self.marking}"
