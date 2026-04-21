from functools import cache
from typing import Iterable

from pysmt.fnode import FNode

from treehornx.chc.post.Tainter import Tainter
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.tainting import TaintedLabel, TaintedPair, TaintingStep
from treehornx.enum_labels import KnittedTrees

@cache
def taint(
    trees: KnittedTrees,
    root_name: str
) -> tuple[set[TaintingStep], set[TaintedLabel], set[TaintedPair]]:
    tainter = Tainter(root_name, trees)
    taint_result = tainter.taint()
    return taint_result

def T_predicates(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]:  # noqa: N803, N802
    _, tainted_labels, _ = taint(trees, root_name)
    for lab in tainted_labels:
        yield T_factory.predicate(lab)


def produce_T_no_query(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]:  # noqa: N803, N802
    tainting_steps, _, _ = taint(trees, root_name)
    for tstep in tainting_steps:
        chc = T_factory.T(tstep)
        yield chc


def produce_T_queries(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]:  # noqa: N803, N802
    _, tainted_labels, tainted_pairs = taint(trees, root_name)
    for lab in tainted_labels:
        yield from T_factory.query(lab)
    for tpair in tainted_pairs:
        yield from T_factory.query(tpair)


def produce_T(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]:  # noqa: N803, N802
    yield from produce_T_no_query(trees, root_name, T_factory)
    yield from produce_T_queries(trees, root_name, T_factory)
