from __future__ import annotations

from dataclasses import dataclass

from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.Dfs.Event import Event
from treehornx.enum_models.Dfs.Flag import State, StateNil
from treehornx.enum_models.Dfs.Inst import Inst
from treehornx.enum_models.Lab.Frame import Frame


@dataclass(slots=True, frozen=True)
class DfsFrame:
    node_state: State
    child_state: tuple[StateNil, ...]
    event: Event
    inst: Inst
    relay: State
    sigma: Label[Frame] | None = None
    """The complete Lab label of the node, set only in the first frame."""


@dataclass(slots=True)
class MutableDfsFrame:
    """A DFS frame under construction, filled phase by phase like `Lab.Frame.MutableFrame`."""

    node_state: State | None = None
    child_state: list[StateNil] | None = None
    event: Event | None = None
    inst: Inst | None = None
    relay: State | None = None

    def to_frozen(self) -> DfsFrame:
        assert self.node_state is not None, "field 'node_state' of the new frame has not been set"
        assert self.child_state is not None, "field 'child_state' of the new frame has not been set"
        assert self.event is not None, "field 'event' of the new frame has not been set"
        assert self.inst is not None, "field 'inst' of the new frame has not been set"
        assert self.relay is not None, "field 'relay' of the new frame has not been set"
        return DfsFrame(self.node_state, tuple(self.child_state), self.event, self.inst, self.relay)
