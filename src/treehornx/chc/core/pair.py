from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import override

from treehornx.chc.core.cache_hash import cache_hash

from .dir import Dir, Down, Internal, Up
from .frame import Frame
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

    def extended_with_internal_frame(self, frame: Frame) -> Pair:
        if self.leadership == LeadershipKind.PARENT:
            if self.parent.frame.prev[0] == Internal():
                assert self.parent.origin is not None, (
                    "Parent label must have an origin to extend with an internal frame if the last frame of the label is an internal step"
                )
                new_parent = self.parent.origin.extended_with(frame)
                return Pair(new_parent, self.child, self.child_key, self.leadership)
            else:
                new_parent = self.parent.extended_with(frame)
                return Pair(new_parent, self.child, self.child_key, self.leadership)
        else:
            if self.child.frame.prev[0] == Internal():
                assert self.child.origin is not None, (
                    "Child label must have an origin to extend with an internal frame if the last frame of the label is an internal step"
                )
                new_child = self.child.origin.extended_with(frame)
                return Pair(self.parent, new_child, self.child_key, self.leadership)
            else:
                new_child = self.child.extended_with(frame)
                return Pair(self.parent, new_child, self.child_key, self.leadership)

    def extended_with_external_frame(self, frame: Frame) -> Pair:
        if self.leadership == LeadershipKind.PARENT:
            new_child = self.child.extended_with(frame)
            return Pair(self.parent, new_child, self.child_key, LeadershipKind.CHILD)
        else:
            new_parent = self.parent.extended_with(frame)
            return Pair(new_parent, self.child, self.child_key, LeadershipKind.PARENT)

    def updated_with_leader(self, new_leader: Label) -> Pair:
        if self.leadership == LeadershipKind.PARENT:
            return Pair(new_leader, self.child, self.child_key, self.leadership)
        else:
            return Pair(self.parent, new_leader, self.child_key, self.leadership)
