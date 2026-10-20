from pathlib import Path

import pytest

from treehornx.chc.Lab import enumerate_labels
from treehornx.enum_models.core.Dir import Down, Internal, Up
from treehornx.enum_models.Lab import LabEngine
from treehornx.enum_models.Lab.helpers import frames_with_prev, linked_frames
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.parser import parse_file

C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24


@pytest.fixture(scope="module", params=[("sll_safe_length", 0), ("bst_safe_insert", 1)], ids=lambda p: p[0])
def engine(request: pytest.FixtureRequest) -> LabEngine:
    program, m = request.param
    function = parse_file(str(C_FILES / f"{program}.c"))
    return enumerate_labels(function, function.node.k, m, N)


def test_next_agrees_with_internal_steps(engine: LabEngine) -> None:
    """A frame followed by an internal step in its label predicted that step, and only that one."""
    for label in engine.states:
        start = 2 if is_initial(label) else 1
        for i in range(start + 1, len(label)):
            assert (label[i].next == Internal()) == (label[i + 1].prev == Internal()), (label, i)


def test_left_frames_have_a_next(engine: LabEngine) -> None:
    """Every frame below the top of a label has been left by the lace, so its direction was predicted."""
    for label in engine.states:
        for i in range(2, len(label)):
            assert label[i].next is not None, (label, i)


def test_predicted_internal_step_exists(engine: LabEngine) -> None:
    for label in engine.states:
        if engine.is_continuos(label) and label.frame.next == Internal():
            assert engine.step_int(label) is not None, label


def test_every_arrival_is_linked(engine: LabEngine) -> None:
    """Each frame of a pair entered from the other node is linked to the frame that sent the lace there."""
    for pair in engine.pairs:
        parent, child, j = pair.parent, pair.child, pair.j
        links = list(linked_frames(parent, child, j))
        assert {c for _, c in links if child[c].prev == Up()} == set(frames_with_prev(child, Up()))
        assert {i for i, _ in links if parent[i].prev == Down(j)} == set(frames_with_prev(parent, Down(j)))
        for i, c in links:
            assert (parent[i].next == Down(j) and child[c].prev == Up()) or (
                child[c].next == Up() and parent[i].prev == Down(j)
            )
