from itertools import product
from typing import Iterable

from treehornx.chc.core import ExitCodeKind
from treehornx.enum_labels import KnittedTrees
from .PreFactory import PreFactory
from .psi import *

def pre_predicates(trees: KnittedTrees, pre_factory: PreFactory) -> Iterable[FNode]:
    for lab in trees.labels():
        yield pre_factory.predicate(lab)

def produce_pre_no_query(trees: KnittedTrees, pre_factory: PreFactory, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]:

    for lab in trees.labels():
        if not lab[0].active and not trees.is_root_label(lab):
            chc = pre_factory.pre_I(lab, exit_codes)
            yield chc

        else:
            pairs_pow_set = [list(trees.pairs_by_parent_and_child_key(lab, key)) for key in trees.child_keys]
            for pairs in product(*pairs_pow_set):
                children = [(child_key, child) for _, child, child_key in pairs]
                chc = pre_factory.pre_II(lab, children, exit_codes)
                yield chc

def produce_pre_queries(trees: KnittedTrees, pre_factory: PreFactory, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]:

    for lab in trees.labels():
        if trees.is_root_label(lab):
            chc = pre_factory.pre_III(lab, exit_codes)
            yield chc

def produce_pre(trees: KnittedTrees, pre_factory: PreFactory, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]:
    yield from produce_pre_no_query(trees, pre_factory, exit_codes)
    yield from produce_pre_queries(trees, pre_factory, exit_codes)
