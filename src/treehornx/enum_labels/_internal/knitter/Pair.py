from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from treehornx.enum_labels._internal.knitter.StepKind import StepKind
from treehornx.enum_labels.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_labels.core.Label import Label


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

    def replace_leader(self, new_leader: Label) -> Pair:
        if self.leadership == LeadershipKind.PARENT:
            return replace(self, parent=new_leader)
        else:
            return replace(self, child=new_leader)

    def last_step_kind(self) -> StepKind | None:
        leader = self.leader()
        if leader.frame.prev is None:
            return None
        elif leader.frame.prev[0] == Internal():
            return StepKind.INTERNAL
        else:
            return StepKind.EXTERNAL
