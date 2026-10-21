"""Orientation of the external steps of the Lab system (CHC IV/V)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pychc.environment import reset_env

from treehornx.chc.Lab import LabCHC, build_lab, external_steps
from treehornx.enum_models.core.Dir import Down, Internal, Up
from treehornx.feature_flags import FeatureFlags
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 128


@pytest.fixture(scope="module")
def lab() -> Iterator[LabCHC]:
    reset_env()
    function = parse_file(str(C_FILES / "bst_unsafe_linked_new.c"))
    yield build_lab(function, function.node.k, 1, N, FeatureFlags())


def test_receiver_follows_sender(lab: LabCHC) -> None:
    """The top frame of the receiver is entered from the direction the top frame of the sender leaves to."""
    for pair in lab.pairs:
        for receiver, sender in external_steps(pair):
            assert (receiver.frame.prev, sender.frame.next) in {(Up(), Down(pair.j)), (Down(pair.j), Up())}


def test_frame_entered_from_parent_and_leaving_to_it(lab: LabCHC) -> None:
    """The new node's frame Here(q) has prev = next = Up: its up-link makes the parent the receiver."""
    bounces = [
        (pair, c)
        for pair in lab.pairs
        for c in range(2, len(pair.child) + 1)
        if pair.child[c].prev == Up() and pair.child[c].next == Up()
    ]
    assert bounces
    for pair, c in bounces:
        senders = [sender for receiver, sender in external_steps(pair) if receiver.frame.prev == Down(pair.j)]
        assert pair.child.cut(c) in senders


def test_every_label_entered_from_another_node_has_a_clause(lab: LabCHC) -> None:
    """Every predicate whose top frame comes from another node is the head of an external clause: the parent
    of the new node, entered from it by s->left = q, is derivable."""
    heads = {clause.arg(1).function_name() for clause in lab.clauses if clause.is_implies()}
    entered = [label for label in lab.predicates if len(label) >= 2 and label.frame.prev != Internal()]
    assert any(label.frame.prev == Down(2) for label in entered)
    for label in entered:
        assert lab.sym.predicate(label) in heads
