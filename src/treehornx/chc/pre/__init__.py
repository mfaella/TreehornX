from itertools import product
from typing import Callable, Iterable

from pysmt.fnode import FNode

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.utils.helpers import end_of_lace
from treehornx.chc.utils.terminals_discovery import Pair, generate_terminals, generate_terminals_from_trees
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Label import Label

from .PreFactory import PreFactory


def pre_predicates(trees: KnittedTrees, pre_factory: PreFactory[Label]) -> Iterable[FNode]:
    for lab in trees.labels():
        yield pre_factory.predicate(lab)


def _pairs_by_parent_and_child_key(
    pairs: set[Pair[Label]], lab: Label, child_key: int | str
) -> Iterable[Pair[Label]]:
    return filter(lambda p: p.parent == lab and p.child_key == child_key, pairs)


def produce_pre_no_query(
    trees: KnittedTrees, pre_factory: PreFactory[Label]
) -> Iterable[FNode]:

    print("calculating terminals...")

    L_Terminal, P_Terminal = generate_terminals_from_trees(trees)  # noqa: N806

    print(f"terminal labels: {len(L_Terminal)}")

    assert not any(p.child_key == "parent" for p in P_Terminal), "Parent key should not be present in P_Terminal"

    for lab in L_Terminal:
        if not lab[0].active and not trees.is_root_label(lab):
            chc = pre_factory.pre_I(lab)
            yield chc

        else:
            pairs_pow_set = [list(_pairs_by_parent_and_child_key(P_Terminal, lab, key)) for key in trees.child_keys if isinstance(key, str)]
            for pairs in product(*pairs_pow_set):
                children = [(p.child_key, p.child) for p in pairs]
                chc = pre_factory.pre_II(lab, children)
                yield chc


def produce_pre_queries(trees: KnittedTrees, pre_factory: PreFactory[Label]) -> Iterable[FNode]:
    L_Terminal, _ = generate_terminals_from_trees(trees)  # noqa: N806

    for lab in L_Terminal:
        if trees.is_root_label(lab):
            chc = pre_factory.pre_III(lab)
            yield chc


def produce_pre(trees: KnittedTrees, pre_factory: PreFactory[Label]) -> Iterable[FNode]:
    yield from produce_pre_no_query(trees, pre_factory)
    yield from produce_pre_queries(trees, pre_factory)
