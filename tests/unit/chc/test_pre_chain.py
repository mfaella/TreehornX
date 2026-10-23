import re
from pathlib import Path

import pytest

from treehornx.chc.Lab import build_lab
from treehornx.chc.pre import PreRunner
from treehornx.chc.sdta.SDTAContext import bst_ctx
from treehornx.chc.smt import sexpr as sx
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24
M = 1
CHAIN = re.compile(r"Pre\d+_\d+")


@pytest.fixture(scope="module")
def runner() -> PreRunner:
    function = parse_file(str(C_FILES / "bst_safe_find.c"))
    lab = build_lab(function, function.node.k, M, N)
    return PreRunner(function, lab.pairs, bst_ctx(), function.node.k, M, sym=lab.sym, n=N)


def test_children_are_collected_one_at_a_time(runner: PreRunner) -> None:
    clauses = list(runner.clauses())
    for clause in clauses:
        body = [b for b in clause.body if isinstance(b, sx.Application)]
        chains = [b for b in body if CHAIN.fullmatch(b.predicate.name)]
        assert len(chains) <= 1, clause
        assert len(body) - len(chains) <= 1, clause
    complete = [by_child for by_child in runner.children.values() if len(by_child) == runner.k + runner.m]
    collected = sum(len(children) for by_child in complete for children in by_child.values())
    collects = [c for c in clauses if isinstance(c.head, sx.Application) and CHAIN.fullmatch(c.head.predicate.name)]
    starts = [c for c in collects if c.head is not False and c.head.predicate.name.endswith("_0")]
    assert len(collects) - len(starts) == collected


def test_chain_predicates_are_declared(runner: PreRunner) -> None:
    declared = set(runner.predicates())
    assert all(re.fullmatch(r"Pre\d+(_\d+)?", p.name) for p in declared)
    used = {app.predicate for clause in [*runner.clauses(), *runner.queries()] for app in clause.applications()}
    assert used <= declared
    assert any(CHAIN.fullmatch(p.name) for p in used)
