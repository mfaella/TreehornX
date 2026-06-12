from functools import cache
from itertools import product
from typing import Iterable

from loguru import logger
from pysmt.fnode import FNode

from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.post.SFactory import SFactory
from treehornx.chc.post.helpers import ptr_here
from treehornx.chc.post.sainting.Sainter import Sainter
from treehornx.chc.post.sainting.core import Q, Acceptance, SaintedLabel, SaintingStep
from treehornx.chc.post.tainting import Tainter
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.tainting import TaintedLabel, TaintedPair, TaintingStep
from treehornx.chc.pre.PreFactory import PreFactory
from treehornx.chc.utils.terminals_discovery import Pair
from treehornx.enum_labels import KnittedTrees

@cache
def _taint(
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
        logger.debug(f"Processing tainted label: {t_factory.label_name(lab)}")
        yield from t_factory.query(lab)
    for tpair in tainted_pairs:
        logger.debug(f"Processing tainted pair: ({t_factory.label_name(tpair.parent)}, {t_factory.label_name(tpair.child)}, {tpair.child_key})")
        yield from t_factory.query(tpair)
    logger.debug("all query T produced")


def produce_T(trees: KnittedTrees, root_name: str, t_factory: TFactory) -> Iterable[FNode]:  # noqa: N802
    yield from produce_T_no_query(trees, root_name, t_factory)
    yield from produce_T_queries(trees, root_name, t_factory)

@cache
def _saint(trees: KnittedTrees, root_name: str) -> tuple[set[SaintingStep], set[SaintedLabel], set[Pair[SaintedLabel]]]:
    logger.debug("sainting begin")
    tainted_labels, tainted_pairs = _taint(trees, root_name)[1:]
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

def produce_S_no_query(trees: KnittedTrees, root_name: str, s_factory: SFactory) -> Iterable[FNode]:  # noqa: N802
    sainting_steps, _, _ = _saint(trees, root_name)
    for sstep in sainting_steps:
        if not isinstance(sstep, Acceptance):
            chc = s_factory.S(sstep)
            yield chc

def _is_automata_run_end(sainted_label: SaintedLabel, root_name: str) -> bool:
    if sainted_label.state_node != Q():
        return False

    for (p, i), state in sainted_label.state_ptr.items():
        if p == root_name and state is True and ptr_here(sainted_label.label, i, root_name):
            return True

    return False


def S_with_Pre_predicates(trees: KnittedTrees, root_name: str, s_factory: SFactory, pre_factory: PreFactory[SaintedLabel]) -> Iterable[FNode]:  # noqa: N802
    yield from S_predicates(trees, root_name, s_factory)

    logger.debug("yielded S predicates")

    _, sainted_labels, _ = _saint(trees, root_name)

    for lab in sainted_labels:
        yield pre_factory.predicate(lab)

    logger.debug("yielded Pre predicates of S")


def _pairs_by_parent_and_child_key[T](
    pairs: set[Pair[T]], lab: T, child_key: int | str
) -> Iterable[Pair[T]]:
    return filter(lambda p: p.parent == lab and p.child_key == child_key, pairs)


def produce_S_with_Pre(trees: KnittedTrees, root_name: str, s_factory: SFactory, pre_factory: PreFactory[SaintedLabel]) -> Iterable[FNode]:  # noqa: N802
    yield from produce_S_no_query(trees, root_name, s_factory)

    _, sainted_labels, sainted_pairs = _saint(trees, root_name)

    logger.debug(f"Total sainted labels: {len(sainted_labels)}")
    for lab in sainted_labels:
        logger.debug(f"Sainted label: {s_factory.label_name(lab)}")

    logger.debug(f"Total sainted pairs: {len(sainted_pairs)}")
    for p in sainted_pairs:
        logger.debug(f"Sainted pair: ({s_factory.label_name(p.parent)}, {s_factory.label_name(p.child)}, {p.child_key})")

    for sainted_lab in sainted_labels:
        logger.debug(f"Processing label: {s_factory.label_name(sainted_lab)}")
        lab = sainted_lab.label
        if not lab[0].active and not trees.is_root_label(lab):
            chc = pre_factory.pre_I(sainted_lab)
            yield chc

        else:
            pairs_pow_set = [list(_pairs_by_parent_and_child_key(sainted_pairs, sainted_lab, key)) for key in trees.child_keys]
            for pairs in product(*pairs_pow_set):
                logger.debug(f"Processing pre automata transition for label {s_factory.label_name(sainted_lab)}: {[f'({p.child_key}, {s_factory.label_name(p.child)})' for p in pairs]}")
                sainted_children = [(p.child_key, p.child) for p in pairs]
                chc = pre_factory.pre_II(sainted_lab, sainted_children)
                yield chc

    for sainted_lab in sainted_labels:
        if trees.is_root_label(sainted_lab.label):
            chc = pre_factory.pre_III(sainted_lab)
            yield chc
