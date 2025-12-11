from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from frozendict import frozendict

from .dir import Dir
from .event import NOP, Event

get_lab_id = count(start=0, step=1).__next__


@dataclass(slots=True, frozen=True, order=True)
class Frame:
    index: int
    active: bool
    pc: int
    upd: frozendict[str, bool]
    isnil: frozendict[str, bool]
    event: Event
    active_child: frozendict[str | int, bool]
    enum_values: frozendict[str, str]
    enum_fields: frozendict[str, str]
    prev: tuple[Dir, int] | None = field(default=None)


@dataclass(slots=True)
class FrameBuilder:
    base: Frame
    index: int = 0
    active: bool | None = None
    pc: int = 0
    upd: dict[str, bool] = field(default_factory=lambda: {})
    isnil: dict[str, bool] = field(default_factory=lambda: {})
    event: Event = field(default=NOP())
    active_child: dict[str | int, bool] = field(default_factory=lambda: {})
    enum_values: dict[str, str] = field(default_factory=lambda: {})
    enum_fields: dict[str, str] = field(default_factory=lambda: {})
    prev: tuple[Dir, int] | None = None

    def __init__(self, base: Frame):
        self.base = base

    def build(self) -> Frame:
        assert self.active is not None
        index = self.index
        active = self.active
        pc = self.pc
        upd: frozendict[str, bool] = frozendict({**self.base.upd, **self.upd})
        isnil: frozendict[str, bool] = frozendict({**self.base.isnil, **self.isnil})
        event = self.event
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
            event=event,
            active_child=active_child,
            enum_values=enum_values,
            enum_fields=enum_fields,
            prev=prev,
        )
