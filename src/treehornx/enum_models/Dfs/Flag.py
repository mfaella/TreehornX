"""Flags of the automaton states in the enumerated part of a DFS frame.

`Q()` stands for "some state of the automaton": its value is not enumerated, it lives in the SMT
variables of the CHC system."""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Bot:
    """⊥: not visited yet."""


@dataclass(slots=True, frozen=True)
class Top:
    """⊤: being visited."""


@dataclass(slots=True, frozen=True)
class Topp:
    """⊤⁺: being visited, root of the output tree."""


@dataclass(slots=True, frozen=True)
class Nil:
    """nil: missing child."""


@dataclass(slots=True, frozen=True)
class Q:
    """A state of the automaton."""


State = Bot | Top | Topp | Q
StateNil = State | Nil
