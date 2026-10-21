"""The engine looks up the links between a parent and its j-th child by their kind (down or up)."""

from pathlib import Path

import pytest

from treehornx.chc.Lab import enumerate_labels
from treehornx.enum_models.core.Dir import Up
from treehornx.enum_models.Lab import Here, LabEngine, Rewind
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24


@pytest.fixture(scope="module")
def engine() -> LabEngine:
    function = parse_file(str(C_FILES / "bst_safe_reenter_child.c"))
    return enumerate_labels(function, function.node.k, 0, N)


def pointer(engine: LabEngine, name: str) -> int:
    return next(p.id for p in engine.function.pointer_vars if p.name == name)


def test_reentering_child_does_not_flag_its_own_update(engine: LabEngine) -> None:
    """The frame entering L again after Here(y) (entered from the root and leaving to it) has upd_y false:
    the updates count from the root frame Here(y) went up to, not from the one that sent the lace to it."""
    y = pointer(engine, "y")
    reentries = [
        label[c + 1]
        for label in engine.states
        for c in range(2, len(label))
        if label[c].event == Here(y) and label[c].prev == Up() and label[c].next == Up() and label[c + 1].prev == Up()
    ]
    assert reentries
    for frame in reentries:
        assert not frame.upd[y], frame


def test_rewind_for_y_stops_in_the_child(engine: LabEngine) -> None:
    """d = y->data finds y in L without rewinding out of it again."""
    y = pointer(engine, "y")
    for label in engine.states:
        frames = list(label)
        for c, f in enumerate(frames[:-1], start=1):
            if f.event == Here(y):
                rewinds = [g for g in frames[c:] if isinstance(g.event, Rewind) and g.next == Up()]
                assert not rewinds, label
