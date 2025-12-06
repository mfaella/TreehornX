from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from typing import Any

from frozendict import frozendict

from .Dir import Dir, Internal
from .Event import NOP, Event

get_lab_id = count(start=0, step=1).__next__


@dataclass(slots=True, frozen=True, order=True)
class Frame:
    index: int
    active: bool
    pc: int
    upd_set: frozenset[str]
    isnil_set: frozenset[str]
    event: Event
    active_child_set: frozenset[str]
    enum_values: frozendict[str, str]
    prev: tuple[Dir, int] | None = field(default=None)
    id: int = field(init=False, hash=False, compare=False, default_factory=get_lab_id)

    def _update_var_set_with_dict(self, var_set: frozenset[str], var_dict: dict[str, bool]) -> frozenset[str]:
        for var, present in var_dict.items():
            if present:
                var_set = var_set.union({var})
            else:
                var_set = var_set.difference({var})
        return var_set

    def updated(
        self,
        index: int | None = None,
        active: bool | None = None,
        pc: int | None = None,
        upd_dict: dict[str, bool] | None = None,
        isnil_dict: dict[str, bool] | None = None,
        event: Event | None = None,
        active_child_dict: dict[str, bool] | None = None,
        enum_values: frozendict[str, str] | None = None,
        prev: tuple[Dir, int] | None = None,
        constraints: Any | None = None,
    ) -> "Frame":
        """
        Return a new Frame with any provided fields replaced.

        Each parameter is optional (may be None). If a parameter is None, the
        value from the original frame is preserved.
        """
        if index is None:
            index = self.index
        if active is None:
            active = self.active
        if pc is None:
            pc = self.pc
        if upd_dict is None:
            upd_set = self.upd_set
        else:
            upd_set = self._update_var_set_with_dict(self.upd_set, upd_dict)
        if isnil_dict is None:
            isnil_set = self.isnil_set
        else:
            isnil_set = self._update_var_set_with_dict(self.isnil_set, isnil_dict)
        if event is None:
            event = self.event
        if active_child_dict is None:
            active_child_set = self.active_child_set
        else:
            active_child_set = self._update_var_set_with_dict(self.active_child_set, active_child_dict)
        if enum_values is None:
            enum_values = self.enum_values
        if prev is None:
            prev = self.prev
        if constraints is None:
            constraints = self.constraints

        return Frame(
            index=index,
            active=active,
            pc=pc,
            upd_set=upd_set,
            isnil_set=isnil_set,
            event=event,
            active_child_set=active_child_set,
            enum_values=enum_values,
            prev=prev,
            constraints=constraints,
        )

    def upd(self, var: str) -> bool:
        return var in self.upd_set

    def isnil(self, var: str) -> bool:
        return var in self.isnil_set

    def active_child(self, var: str) -> bool:
        return var in self.active_child_set
