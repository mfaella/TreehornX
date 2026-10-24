"""Errors of a pair raise the flag of the parent, accumulated over its children up to the root query."""

from dataclasses import dataclass
from pathlib import Path

import pytest
from typing_extensions import override

from treehornx.chc.Lab import build_lab
from treehornx.chc.pre import PreRunner
from treehornx.chc.sdta.SDTAContext import true_ctx
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.Lab import Lab
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24
MARKER = "pair_error"


@dataclass
class MarkedRunner(PreRunner):
    """Every link to a child with index 0 is an error, read from a symbol of the child."""

    @override
    def is_pair_error(self, parent: Lab, child: Lab, j: int, parent_prefix: str, child_prefix: str) -> sx.SExpr:
        return sx.Var(f"{child_prefix}{MARKER}", sx.Type.Bool) if j == 0 else sx.FALSE


@pytest.fixture(scope="module")
def runners() -> tuple[PreRunner, MarkedRunner]:
    function = parse_file(str(C_FILES / "sll_safe_find.c"))
    k = function.node.k
    lab = build_lab(function, k, 0, N)
    plain = PreRunner(function, lab.pairs, true_ctx(), k, 0, sym=lab.sym, n=N)
    marked = MarkedRunner(function, lab.pairs, true_ctx(), k, 0, sym=lab.sym, n=N)
    return plain, marked


def test_no_pair_error_by_default(runners: tuple[PreRunner, MarkedRunner]) -> None:
    plain, _ = runners
    assert all(MARKER not in clause.to_smt() for clause in plain.clauses())


def test_pair_error_raises_the_flag_of_the_parent(runners: tuple[PreRunner, MarkedRunner]) -> None:
    _, marked = runners
    collects = [
        marked.collect_clause(parent, child, j)
        for parent, by_child in marked.children.items()
        for j, children in by_child.items()
        for child in children
    ]
    assert collects
    for clause in collects:
        assert isinstance(clause.head, sx.Application)
        j = int(clause.head.predicate.name.rsplit("_", 1)[1]) - 1
        flag = marked.chain_error_symbol(j + 1)
        (update,) = [b for b in clause.body if isinstance(b, sx.OpExpr) and flag in b.args]
        assert (f"c0_{MARKER}" in update.to_smt()) == (j == 0)
