from itertools import product
from typing import Iterable

from pysmt.fnode import FNode

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.Tainter import Tainter
from treehornx.enum_labels import KnittedTrees

def T_predicates(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]: # noqa: N803, N802
    tainter = Tainter(root_name, trees)
    _, tainted_labels, _ = tainter.taint()
    for lab in tainted_labels:
        yield T_factory.predicate(lab)

def produce_T_no_query(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]: # noqa: N803, N802
    tainter = Tainter(root_name, trees)
    tainting_steps, _, _ = tainter.taint()
    for tstep in tainting_steps:
        chc = T_factory.T(tstep)
        yield chc

def produce_T_queries(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]: # noqa: N803, N802
    tainter = Tainter(root_name, trees)
    _, tainted_labels, tainted_pairs = tainter.taint()
    for lab in tainted_labels:
        yield from T_factory.query(lab)
    for tpair in tainted_pairs:
        yield from T_factory.query(tpair)

def produce_T(trees: KnittedTrees, root_name: str, T_factory: TFactory) -> Iterable[FNode]: # noqa: N803, N802
    yield from produce_T_no_query(trees, root_name, T_factory)
    yield from produce_T_queries(trees, root_name, T_factory)
