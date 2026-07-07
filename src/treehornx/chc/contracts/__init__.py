
from itertools import product
from typing import Callable, Iterable

from pysmt.fnode import FNode
import pysmt.shortcuts as smt
import pychc.shortcuts as chc

from treehornx.chc.contracts.Contract import Contract
from treehornx.chc.post import taint
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.tainting.core import TaintedLabel
from treehornx.chc.pre.PreFactory import PreFactory
from treehornx.chc.utils.terminals_discovery import Pair, generate_terminals_from_trees
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Label import Label

def produce_contract_queries(trees: KnittedTrees, contract: Contract[TaintedLabel], t_factory: TFactory) -> Iterable[FNode]:
    _, tlabels, _ = taint(trees, trees.root_name)
    for lab in tlabels:
        body = smt.And(t_factory.apply(lab), contract.failure_check(lab, t_factory.fragment_factory, ""))
        clause = chc.Clause(body, smt.FALSE())
        yield clause

def _make_parent_child_key_index[T](pairs: set[Pair[T]]) -> dict[tuple[T, int | str], list[Pair[T]]]:
    index: dict[tuple[T, int | str], list[Pair[T]]] = {}
    for p in pairs:
        key = (p.parent, p.child_key)
        if key not in index:
            index[key] = []
        index[key].append(p)
    return index

def produce_contract_with_Pre(trees: KnittedTrees, pre_factory: PreFactory[TaintedLabel], parent: None | str = None) -> Iterable[FNode]:  # noqa: N802
    _, tlabels, tpairs_ = taint(trees, trees.root_name)
    tpairs = set(Pair(p.parent, p.child, p.child_key) for p in tpairs_)

    parent_child_key_index = _make_parent_child_key_index(tpairs)

    for tlab in tlabels:
        label = tlab.label
        if not label[0].active and not trees.is_root_label(label):
            chc = pre_factory.pre_I(tlab)
            yield chc

        else:
            pairs_pow_set = [parent_child_key_index[(tlab, key)] for key in trees.child_keys if key != parent]
            for pairs in product(*pairs_pow_set):
                # logger.debug(f"Processing pre automata transition for label {t_factory.label_name(tlab)}: {[f'({p.child_key}, {s_factory.label_name(p.child)})' for p in pairs]}")
                t_children = [(p.child_key, p.child) for p in pairs]
                chc = pre_factory.pre_II(tlab, t_children)
                yield chc

    for tlab in tlabels:
        if trees.is_root_label(tlab.label):
            chc = pre_factory.pre_III(tlab)
            yield chc

def constract_with_Pre_predicates(trees: KnittedTrees, pre_factory: PreFactory[TaintedLabel]) -> Iterable[FNode]:
    _, tlabels, _ = taint(trees, trees.root_name)
    for tlab in tlabels:
        yield pre_factory.predicate(tlab)
