"""Events of the DFS lace.

`TFWD` and `InitTFWD` hold a position in the Lab label of the node, `SFWD` a position in its DFS label."""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class NOP:
    pass


@dataclass(slots=True, frozen=True)
class TFWD:
    """Taint forwarding, rewinding the Lab lace from position i."""

    i: int


@dataclass(slots=True, frozen=True)
class InitTFWD:
    """Start of a taint forwarding for the pointer field assigned at the Lab position i."""

    i: int


@dataclass(slots=True, frozen=True)
class SFWD:
    """State forwarding, back to the DFS position i."""

    i: int


@dataclass(slots=True, frozen=True)
class StructTaint:
    pass


@dataclass(slots=True, frozen=True)
class RemoteTaint:
    pass


@dataclass(slots=True, frozen=True)
class Dang:
    """A dangling node is reached."""


@dataclass(slots=True, frozen=True)
class Loop:
    """A node is reached while it is being visited."""


@dataclass(slots=True, frozen=True)
class Conv:
    """A node is reached twice."""


@dataclass(slots=True, frozen=True)
class SelfLoop:
    """A pointer field points to its own node."""


@dataclass(slots=True, frozen=True)
class Acc:
    """The automaton accepts the output tree."""


Event = NOP | TFWD | InitTFWD | SFWD | StructTaint | RemoteTaint | Dang | Loop | Conv | SelfLoop | Acc

TREE_ERRORS = (Dang, Loop, Conv, SelfLoop)
ERR_EVENTS = (*TREE_ERRORS, Acc)
