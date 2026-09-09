from collections import defaultdict
from functools import cache
from itertools import product
from typing import Iterable

from loguru import logger
from pysmt.fnode import FNode

from treehornx.chc.post.SFactory import SFactory
from treehornx.chc.post.helpers import ptr_here
from treehornx.chc.post.sainting.Sainter import Sainter
from treehornx.chc.post.sainting.core import Q, EmptyAcceptance, NonEmptyAcceptance, SaintedLabel, SaintingStep
from treehornx.chc.post.tainting import Tainter
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.tainting import TaintedLabel, TaintedPair, TaintingStep
from treehornx.chc.pre.PreFactory import PreFactory
from treehornx.chc.utils.terminals_discovery import Pair
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.helpers import is_pfield_implicit, is_pfield_nil

@cache
def taint(
    trees: KnittedTrees,
    root_name: str
) -> tuple[set[TaintingStep], set[TaintedLabel], set[TaintedPair]]:
    logger.debug("taint begin")
    tainter = Tainter(root_name, trees)
    taint_result = tainter.taint()
    logger.debug("taint end")
    logger.debug(f"Tainted labels: {len(taint_result[1])}")
    for tlab in taint_result[1]:
        logger.debug(f"tainted label: {tainter.label_name(tlab)}")
    for tpair in taint_result[2]:
        logger.debug(f"tainted pair: ({tainter.label_name(tpair.parent)}, {tainter.label_name(tpair.child)}, {tpair.child_key})")
    logger.debug(f"Tainted pairs: {len(taint_result[2])}")
    return taint_result

def T_predicates(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    _, tainted_labels, _ = taint(trees, root_name)
    for lab in tainted_labels:
        yield t_factory.predicate(lab)


def produce_T_no_query(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    tainting_steps, _, _ = taint(trees, root_name)
    for tstep in tainting_steps:
        chc = t_factory.T(tstep)
        yield chc


def produce_T_queries(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    _, tainted_labels, tainted_pairs = taint(trees, root_name)
    for lab in tainted_labels:
        logger.debug(f"Processing tainted label: {t_factory.label_name(lab)}")
        yield from t_factory.query(lab)
    for tpair in tainted_pairs:
        logger.debug(f"Processing tainted pair: ({t_factory.label_name(tpair.parent)}, {t_factory.label_name(tpair.child)}, {tpair.child_key})")
        yield from t_factory.query(tpair)
    logger.debug("all query T produced")


def produce_T(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    yield from produce_T_no_query(trees, root_name, t_factory)
    yield from produce_T_queries(trees, root_name, t_factory)

def is_final_tainted_label(tainted_label: TaintedLabel) -> bool:
    label = tainted_label.label

    if not label.frame.active:
        return False

    children_keys = list( key for key in label.frame.active_child.keys() if isinstance(key, str))
    return all(
        (is_pfield_implicit(label, key) and not label.frame.active_child[key]) or
        is_pfield_nil(label, key)
        for key in children_keys
    )

@cache
def _saint(trees: KnittedTrees, root_name: str, parent: str | None = None) -> tuple[set[SaintingStep], set[SaintedLabel], set[Pair[SaintedLabel]]]:
    logger.debug("sainting begin")
    tainted_labels, tainted_pairs = taint(trees, root_name)[1:]
    sainter = Sainter(trees, tainted_labels, tainted_pairs)
    sainting_steps, sainted_label, sainted_pairs = sainter.saint()
    logger.debug("sainting end")
    return sainting_steps, sainted_label, sainted_pairs

def S_predicates(trees: KnittedTrees, root_name: str, s_factory: SFactory) -> Iterable[FNode]:  # noqa: N802
    _, sainted_labels, _ = _saint(trees, root_name)
    for lab in sainted_labels:
        logger.debug(f"yielding predicate of {s_factory.label_name(lab)}")
        yield s_factory.predicate(lab)

def produce_S(trees: KnittedTrees, root_name: str, s_factory: SFactory) -> Iterable[FNode]:  # noqa: N802
    sainting_steps, _, _ = _saint(trees, root_name)
    return s_factory.all_S(sainting_steps)

def produce_S_no_query(trees: KnittedTrees, root_name: str, s_factory: SFactory, parent: str | None = None) -> Iterable[FNode]:  # noqa: N802
    sainting_steps, _, _ = _saint(trees, root_name, parent=parent)
    for sstep in sainting_steps:
        if not isinstance(sstep, (EmptyAcceptance, NonEmptyAcceptance)):
            chc = s_factory.S(sstep)
            yield chc

def S_with_Pre_predicates(trees: KnittedTrees, root_name: str, s_factory: SFactory, pre_factory: PreFactory[SaintedLabel]) -> Iterable[FNode]:  # noqa: N802
    yield from S_predicates(trees, root_name, s_factory)

    logger.debug("yielded S predicates")

    _, sainted_labels, _ = _saint(trees, root_name)

    for lab in sainted_labels:
        yield pre_factory.predicate(lab)

    logger.debug("yielded Pre predicates of S")

def _make_parent_child_key_index[T](pairs: set[Pair[T]]) -> defaultdict[tuple[T, int | str], list[Pair[T]]]:
    index: dict[tuple[T, int | str], list[Pair[T]]] = {}
    for p in pairs:
        key = (p.parent, p.child_key)
        if key not in index:
            index[key] = []
        index[key].append(p)
    return defaultdict(list, index)

def produce_S_with_Pre(trees: KnittedTrees, root_name: str, s_factory: SFactory, pre_factory: PreFactory[SaintedLabel], parent: str | None = None) -> Iterable[FNode]:  # noqa: N802
    yield from produce_S_no_query(trees, root_name, s_factory, parent=parent)

    _, sainted_labels, sainted_pairs = _saint(trees, root_name)

    # logger.debug(f"Total sainted labels: {len(sainted_labels)}")
    # for lab in sainted_labels:
    #     logger.debug(f"Sainted label: {s_factory.label_name(lab)}")

    # logger.debug(f"Total sainted pairs: {len(sainted_pairs)}")
    # for p in sainted_pairs:
    #     logger.debug(f"Sainted pair: ({s_factory.label_name(p.parent)}, {s_factory.label_name(p.child)}, {p.child_key})")

    parent_child_key_index = _make_parent_child_key_index(sainted_pairs)
    for sainted_lab in sainted_labels:
        logger.debug(f"Processing label: {s_factory.label_name(sainted_lab)}")
        lab = sainted_lab.label
        if not lab[0].active and not trees.is_root_label(lab):
            chc = pre_factory.pre_I(sainted_lab)
            yield chc

        else:
            pairs_pow_set = [parent_child_key_index[(sainted_lab, key)] for key in trees.child_keys if key != parent]
            for pairs in product(*pairs_pow_set):
                logger.debug(f"Processing pre automata transition for label {s_factory.label_name(sainted_lab)}: {[f'({p.child_key}, {s_factory.label_name(p.child)})' for p in pairs]}")
                sainted_children = [(p.child_key, p.child) for p in pairs]
                chc = pre_factory.pre_II(sainted_lab, sainted_children)
                yield chc

    for sainted_lab in sainted_labels:
        if trees.is_root_label(sainted_lab.label):
            chc = pre_factory.pre_III(sainted_lab)
            yield chc
