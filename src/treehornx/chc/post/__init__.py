from functools import cache
from typing import Iterable

from pysmt.fnode import FNode

from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.post.SFactory import SFactory
from treehornx.chc.post.sainting.Sainter import Sainter
from treehornx.chc.post.sainting.core import SaintedLabel, SaintingStep
from treehornx.chc.post.tainting import Tainter
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.tainting import TaintedLabel, TaintedPair, TaintingStep
from treehornx.enum_labels import KnittedTrees

@cache
def _taint(
    trees: KnittedTrees,
    root_name: str
) -> tuple[set[TaintingStep], set[TaintedLabel], set[TaintedPair]]:
    tainter = Tainter(root_name, trees)
    taint_result = tainter.taint()
    print(f"Tainted labels: {len(taint_result[1])}")
    print(f"Tainted pairs: {len(taint_result[2])}")
    return taint_result

def T_predicates(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    _, tainted_labels, _ = _taint(trees, root_name)
    for lab in tainted_labels:
        yield t_factory.predicate(lab)


def produce_T_no_query(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    tainting_steps, _, _ = _taint(trees, root_name)
    for tstep in tainting_steps:
        chc = t_factory.T(tstep)
        yield chc


def produce_T_queries(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    _, tainted_labels, tainted_pairs = _taint(trees, root_name)
    for lab in tainted_labels:
        yield from t_factory.query(lab)
    for tpair in tainted_pairs:
        yield from t_factory.query(tpair)


def produce_T(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    yield from produce_T_no_query(trees, root_name, t_factory)
    yield from produce_T_queries(trees, root_name, t_factory)

@cache
def _saint(trees: KnittedTrees, root_name: str) -> tuple[set[SaintingStep], set[SaintedLabel]]:
    tainted_labels, tainted_pairs = _taint(trees, root_name)[1:]
    sainter = Sainter(trees, tainted_labels, tainted_pairs)
    sainting_steps, sainted_label, _ = sainter.saint()
    return sainting_steps, sainted_label

def S_predicates(trees: KnittedTrees, root_name: str, s_factory: SFactory) -> Iterable[FNode]:  # noqa: N802
    _, sainted_labels = _saint(trees, root_name)
    for lab in sainted_labels:
        yield s_factory.predicate(lab)

def produce_S(trees: KnittedTrees, root_name: str, s_factory: SFactory) -> Iterable[FNode]:  # noqa: N802
    sainting_steps, _ = _saint(trees, root_name)
    return s_factory.all_S(sainting_steps)
