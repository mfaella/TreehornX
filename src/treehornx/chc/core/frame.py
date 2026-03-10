from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from frozendict import frozendict

from treehornx.chc.core.cache_hash import cache_hash

from .dir import Dir, Internal
from .event import NOP, Event

get_lab_id = count(start=0, step=1).__next__


@dataclass(frozen=True, order=True)
class Frame:
    index: int  # independent
    active: bool
    pc: int  # independent
    upd: frozendict[str, bool]
    isnil: frozendict[str, bool]  # independent
    events: frozenset[Event]
    active_child: frozendict[str | int, bool]  # independent
    enum_values: frozendict[str, str]  # independent
    enum_fields: frozendict[str, str]  # independent
    prev: tuple[Dir, int] | None = field(default=None)  # independent


@dataclass(slots=True)
class FrameBuilder:
    base: Frame
    index: int = 0
    active: bool | None = None
    pc: int = 0
    upd: dict[str, bool] = field(default_factory=lambda: {})
    isnil: dict[str, bool] = field(default_factory=lambda: {})
    events: set[Event] = field(default_factory=set)
    active_child: dict[str | int, bool] = field(default_factory=lambda: {})
    enum_values: dict[str, str] = field(default_factory=lambda: {})
    enum_fields: dict[str, str] = field(default_factory=lambda: {})
    prev: tuple[Dir, int] | None = None

    def build(self) -> Frame:
        assert self.active is not None
        index = self.index
        active = self.active
        pc = self.pc
        upd: frozendict[str, bool] = frozendict({**self.base.upd, **self.upd})
        isnil: frozendict[str, bool] = frozendict({**self.base.isnil, **self.isnil})
        if self.prev[0] == Internal() and self.base is not None:
            events = frozenset(self.base.events) | frozenset(self.events)
        else:
            events = frozenset(self.events)
        active_child: frozendict[str | int, bool] = frozendict({**self.base.active_child, **self.active_child})
        enum_values = self.base.enum_values | self.enum_values
        enum_fields = self.base.enum_fields | self.enum_fields
        prev = self.prev
        return Frame(
            index=index,
            active=active,
            pc=pc,
            upd=upd,
            isnil=isnil,
            events=events,
            active_child=active_child,
            enum_values=enum_values,
            enum_fields=enum_fields,
            prev=prev,
        )
