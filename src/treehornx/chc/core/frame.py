from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from frozendict import frozendict

from treehornx.chc.core.cache_hash import cache_hash

from .dir import Dir, Internal
from .event import NOP, Event, FieldAssignP, Here


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
    prev: tuple[Dir, int] | None  # independent


@dataclass(slots=True)
class FrameDescriptor:
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
