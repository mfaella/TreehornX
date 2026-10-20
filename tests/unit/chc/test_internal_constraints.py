from collections.abc import Iterator
from pathlib import Path

import pytest
from pychc.environment import reset_env

from treehornx.chc.clean import conjuncts
from treehornx.chc.Lab import LabCHC, build_lab, initial_constraints, internal_constraints, psi_internal
from treehornx.chc.Lab.clauses import SIGMA_PREFIX
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.Lab import Lab
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.parser import parse_file

C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24


@pytest.fixture(scope="module")
def lab() -> Iterator[LabCHC]:
    """The system is built once for the module, so the flag is patched for the module too."""
    reset_env()
    function = parse_file(str(C_FILES / "sll_safe_length.c"))
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("treehornx.chc.clean.ENABLE_CLEAN_CLAUSE", True)
        yield build_lab(function, function.node.k, 0, N)


def is_internal(label: Lab) -> bool:
    return label.frame.prev == Internal()


def test_one_block_per_internal_frame(lab: LabCHC) -> None:
    for label in lab.predicates:
        expected = []
        for i in range(2, len(label) + 1):
            prefix = label.cut(i)
            if not is_internal(prefix):
                continue
            if i == 2 and is_initial(prefix):
                expected += initial_constraints(lab.sym)
            else:
                expected += psi_internal(lab.sym, prefix)
        assert internal_constraints(lab.sym, label) == expected


def test_initial_frame_copies_the_fields(lab: LabCHC) -> None:
    initial = [label for label in lab.predicates if len(label) == 2 and is_initial(label)]
    assert initial
    for label in initial:
        assert internal_constraints(lab.sym, label) == initial_constraints(lab.sym)


def test_dropped_frames_are_constrained(lab: LabCHC) -> None:
    """The frames dropped from a predicate only occur in the constraints, so they are quantified variables."""
    dropped = [label for label in lab.predicates if len(lab.sym.kept_frames(label)) < len(label)]
    assert dropped, "the program has no internal chain long enough to drop a frame"
    for label in dropped:
        arguments = set(lab.sym.label_symbols(label))
        constrained = {s for c in internal_constraints(lab.sym, label) for s in c.get_free_variables()}
        for i in range(1, len(label) + 1):
            if i in lab.sym.kept_frames(label):
                continue
            # a variable overwritten by the next step can stay free, but every dropped frame is constrained
            frame = set(lab.sym.frame_symbols(i))
            assert not frame & arguments
            assert frame & constrained, f"frame {i} of a label of length {len(label)} is not constrained"


def test_external_top_frame_adds_no_constraint(lab: LabCHC) -> None:
    for label in lab.predicates:
        if label.prefix is not None and not is_internal(label):
            assert internal_constraints(lab.sym, label, SIGMA_PREFIX) == internal_constraints(
                lab.sym, label.prefix, SIGMA_PREFIX
            )


def test_clauses_have_no_top_level_variable_equality(lab: LabCHC) -> None:
    for clause in lab.clauses:
        if not clause.is_implies():
            continue
        for c in conjuncts(clause.arg(0)):
            if c.is_equals() or c.is_iff():
                assert not all(arg.is_symbol() for arg in c.args()), c
