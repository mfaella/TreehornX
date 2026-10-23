from collections.abc import Iterator
from pathlib import Path

import pytest

from treehornx.chc.Lab import (
    LabCHC,
    build_lab,
    initial_constraints,
    label_constraints,
    psi_internal,
    to_system,
)
from treehornx.chc.pre import PreRunner
from treehornx.chc.sdta.SDTAContext import true_ctx
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.Lab import Lab
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24


@pytest.fixture(scope="module")
def lab() -> Iterator[LabCHC]:
    """The labels are enumerated once for the module."""
    function = parse_file(str(C_FILES / "sll_safe_length.c"))
    yield build_lab(function, function.node.k, 0, N)


def is_internal(label: Lab) -> bool:
    return label.frame.prev == Internal()


def prefixes(lab: LabCHC) -> set[Lab]:
    return {label.cut(i) for label in lab.labels for i in range(1, len(label) + 1)}


def fields_below(lab: LabCHC, label: Lab) -> list[sx.SExpr]:
    b = len(label)
    return [
        sx.OpExpr(sx.Operator.EQ, f_b, f_below)
        for f_b, f_below in zip(lab.sym.field_symbols(b), lab.sym.field_symbols(b - 1))
    ]


def test_one_block_per_frame(lab: LabCHC) -> None:
    for label in prefixes(lab):
        expected: list[sx.SExpr] = []
        for i in range(2, len(label) + 1):
            prefix = label.cut(i)
            if not is_internal(prefix):
                expected += fields_below(lab, prefix)
            elif i == 2 and is_initial(prefix):
                expected += initial_constraints(lab.sym)
            else:
                expected += psi_internal(lab.sym, prefix)
        assert label_constraints(lab.sym, label) == expected


def test_initial_frame_copies_the_fields(lab: LabCHC) -> None:
    initial = [label for label in prefixes(lab) if len(label) == 2 and is_initial(label)]
    assert initial
    for label in initial:
        assert label_constraints(lab.sym, label) == initial_constraints(lab.sym)


def test_external_top_frame_copies_the_fields(lab: LabCHC) -> None:
    """A frame reached from another node keeps the data fields of the frame below in the same node."""
    external = [label for label in prefixes(lab) if label.prefix is not None and not is_internal(label)]
    assert external
    for label in external:
        assert label.prefix is not None
        expected = label_constraints(lab.sym, label.prefix) + fields_below(lab, label)
        assert label_constraints(lab.sym, label) == expected


def test_dropped_frames_are_constrained(lab: LabCHC) -> None:
    """The frames dropped from a predicate only occur in the constraints, so they are quantified variables."""
    dropped = [label for label in prefixes(lab) if len(lab.sym.kept_frames(label)) < len(label)]
    assert dropped, "the program has no internal chain long enough to drop a frame"
    for label in dropped:
        arguments = set(lab.sym.label_symbols(label))
        constrained = {s for c in label_constraints(lab.sym, label) for s in c.free_variables()}
        for i in range(1, len(label) + 1):
            if i in lab.sym.kept_frames(label):
                continue
            # a variable overwritten by the next step can stay free, but every dropped frame is constrained
            frame = set(lab.sym.frame_symbols(i))
            assert not frame & arguments
            assert frame & constrained, f"frame {i} of a label of length {len(label)} is not constrained"


def variable_equalities(clause: sx.Clause) -> list[sx.SExpr]:
    return [
        c
        for c in clause.body
        if isinstance(c, sx.OpExpr) and c.op is sx.Operator.EQ and all(isinstance(arg, sx.Var) for arg in c.args)
    ]


def test_clauses_are_cleaned_only_when_printed(lab: LabCHC) -> None:
    function = lab.sym.function
    runner = PreRunner(function, lab.pairs, true_ctx(), function.node.k, 0, sym=lab.sym, n=N)
    system = to_system(runner.predicates(), [*runner.clauses(), *runner.queries()], clean=True)
    assert any(variable_equalities(clause) for clause in system.clauses), "the built clauses are not cleaned"
    for clause in system.printed_clauses():
        assert not variable_equalities(clause), clause
