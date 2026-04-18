from itertools import product
from typing import Iterable

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.utils.terminals_discovery import generate_L_P_Terminal
from treehornx.enum_labels import KnittedTrees
from .PreFactory import PreFactory
from .psi import *

def pre_predicates(trees: KnittedTrees, pre_factory: PreFactory) -> Iterable[FNode]:
    for lab in trees.labels():
        yield pre_factory.predicate(lab)

def _pairs_by_parent_and_child_key(pairs: set[tuple[Label, Label, str|int]], lab: Label, child_key: int | str) -> Iterable[tuple[Label, Label, int | str]]:
    return filter(lambda p: p[0] == lab and p[2] == child_key, pairs)

def produce_pre_no_query(trees: KnittedTrees, pre_factory: PreFactory, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]:

    L_Terminal, P_Terminal = generate_L_P_Terminal(trees) # noqa: N806

    for lab in L_Terminal:
        if not lab[0].active and not trees.is_root_label(lab):
            chc = pre_factory.pre_I(lab, exit_codes)
            yield chc

        else:
            pairs_pow_set = [list(_pairs_by_parent_and_child_key(P_Terminal, lab, key)) for key in trees.child_keys]
            for pairs in product(*pairs_pow_set):
                children = [(child_key, child) for _, child, child_key in pairs]
                chc = pre_factory.pre_II(lab, children, exit_codes)
                yield chc

def produce_pre_queries(trees: KnittedTrees, pre_factory: PreFactory, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]:

    L_Terminal, _ = generate_L_P_Terminal(trees) # noqa: N806

    for lab in L_Terminal:
        if trees.is_root_label(lab):
            chc = pre_factory.pre_III(lab, exit_codes)
            yield chc

def produce_pre(trees: KnittedTrees, pre_factory: PreFactory, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]:
    yield from produce_pre_no_query(trees, pre_factory, exit_codes)
    yield from produce_pre_queries(trees, pre_factory, exit_codes)
