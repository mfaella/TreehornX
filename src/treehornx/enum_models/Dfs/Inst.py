"""Instructions of the DFS lace: the step the next frame performs."""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class NoInst:
    pass


@dataclass(slots=True, frozen=True)
class FindP:
    """Find the node pointed by the pointer variable p."""

    p: int


@dataclass(slots=True, frozen=True)
class VisitNext:
    pass


@dataclass(slots=True, frozen=True)
class Trans:
    pass


@dataclass(slots=True, frozen=True)
class PushState:
    pass


@dataclass(slots=True, frozen=True)
class StateForward:
    pass


@dataclass(slots=True, frozen=True)
class Accept:
    pass


Inst = NoInst | FindP | VisitNext | Trans | PushState | StateForward | Accept
