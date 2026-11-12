from dataclasses import dataclass
from typing import Generic, TypeVar


S = TypeVar("S")
C = TypeVar("C")


@dataclass(frozen=True, slots=True)
class Edge(Generic[S, C]):
    """An edge of a symbolic tree: the state of a parent, the state of its child and the index of the child."""

    parent: S
    child: S
    j: C


Pair = Edge[S, int]
"""An edge whose child index is an int."""
