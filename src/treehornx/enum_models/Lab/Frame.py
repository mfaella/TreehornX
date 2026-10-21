from __future__ import annotations

from dataclasses import dataclass

from treehornx.enum_models.core.Dir import Dir
from treehornx.enum_models.Lab.Event import Event


@dataclass(slots=True, frozen=True)
class Frame:
    active: bool
    pc: int
    upd: tuple[bool, ...]
    isnil: tuple[bool, ...]
    event: Event
    active_child: tuple[bool, ...]
    prev: Dir | None
    # direction in which the lace leaves the frame, None when it never does
    next: Dir | None

    def to_mut(self) -> MutableFrame:
        return MutableFrame(
            self.active,
            self.pc,
            list(self.upd),
            list(self.isnil),
            self.event,
            list(self.active_child),
            self.prev,
            self.next,
        )


@dataclass(slots=True)
class MutableFrame:
    """A frame under construction.

    Every field starts unset (None) and is filled phase by phase: first by the step that
    sets the fields specific to the instruction, then by `default` for the remaining ones
    and finally by the Psi predicate that computes `upd`. `to_frozen` checks that no field
    has been forgotten."""

    active: bool | None = None
    pc: int | None = None
    upd: list[bool] | None = None
    isnil: list[bool] | None = None
    event: Event | None = None
    active_child: list[bool] | None = None
    prev: Dir | None = None
    # set last, by predict_next_dir; None is a valid value (the lace never leaves the frame)
    next: Dir | None = None

    def to_frozen(self) -> Frame:
        assert self.active is not None, "field 'active' of the new frame has not been set"
        assert self.pc is not None, "field 'pc' of the new frame has not been set"
        assert self.upd is not None, "field 'upd' of the new frame has not been set"
        assert self.isnil is not None, "field 'isnil' of the new frame has not been set"
        assert self.event is not None, "field 'event' of the new frame has not been set"
        assert self.active_child is not None, "field 'active_child' of the new frame has not been set"
        assert self.prev is not None, "field 'prev' of the new frame has not been set"
        return Frame(
            self.active,
            self.pc,
            tuple(self.upd),
            tuple(self.isnil),
            self.event,
            tuple(self.active_child),
            self.prev,
            self.next,
        )
