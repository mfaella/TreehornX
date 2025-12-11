from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import override

from .dir import Dir, Down, Up
from .label import Label


class LeadershipKind(Enum):
    PARENT = 1
    CHILD = 2

    def opposite(self) -> LeadershipKind:
        if self == LeadershipKind.PARENT:
            return LeadershipKind.CHILD
        else:
            return LeadershipKind.PARENT


@dataclass(frozen=True)
class Pair:
    parent: Label
    child: Label
    child_key: str | int
    leadership: LeadershipKind = LeadershipKind.PARENT

    def leader(self) -> Label:
        if self.leadership == LeadershipKind.PARENT:
            return self.parent
        else:
            return self.child

    def follower(self) -> Label:
        if self.leadership == LeadershipKind.PARENT:
            return self.child
        else:
            return self.parent

    def dir(self) -> Dir:
        if self.leadership == LeadershipKind.PARENT:
            return Down(self.child_key)
        else:
            return Up()

    def rev_dir(self) -> Dir:
        if self.leadership == LeadershipKind.PARENT:
            return Up()
        else:
            return Down(self.child_key)
