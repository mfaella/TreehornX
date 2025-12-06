from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import override

from .Label import Label


class Leadership(Enum):
    PARENT = 1
    CHILD = 2


@dataclass(frozen=True)
class Pair(ABC):
    parent: Label
    child: Label
    child_index: int

    @abstractmethod
    def leader(self) -> Label: ...

    @abstractmethod
    def follower(self) -> Label: ...

    @abstractmethod
    def leadership(self) -> Enum: ...


@dataclass(frozen=True)
class ParentLedPair(Pair):
    @override
    def leader(self) -> Label:
        return self.parent

    @override
    def follower(self) -> Label:
        return self.child

    @override
    def leadership(self) -> Enum:
        return Leadership.PARENT


@dataclass(frozen=True)
class ChildLedPair(Pair):
    @override
    def leader(self) -> Label:
        return self.child

    @override
    def follower(self) -> Label:
        return self.parent

    @override
    def leadership(self) -> Enum:
        return Leadership.CHILD
