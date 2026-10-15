"""Compressed CHC system of the Lab encoding."""

from dataclasses import dataclass, field
from typing import Callable, Iterable

from pychc.chc_system import CHCSystem
from pysmt import logics
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.clauses import external_clause, fact, internal_clause, query
from treehornx.chc.Lab.symbols import predicate
from treehornx.enum_models.core.Dir import Down, Internal, Up
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab import Frame, Lab, LabEngine, backbone_labels, initial_pairs, start_labels
from treehornx.enum_models.Lab.helpers import next_of, prev_of
from treehornx.enum_models.Lab.initial import is_initial


def enumerate_labels(function: ir.Function, k: int, m: int, n: int) -> LabEngine:
    assert k == function.node.k, f"k = {k} differs from the number of pointer fields {function.node.k}"
    starts = set(start_labels(function, m))
    backbones = set(backbone_labels(function, m))
    engine = LabEngine(
        k,
        m,
        n,
        initial_pairs=set(initial_pairs(function, m, starts, backbones)),
        start_labels=starts,
        function=function,
    )
    engine.fix()
    return engine


def external_steps(pair: Pair[Frame]) -> list[tuple[Lab, Lab]]:
    """Every step between the two labels of the pair, as (receiver, sender) prefixes, from the latest one.

    A step is a link between a frame τ^b and the frame σ^a it follows in the lace (CHC IV/V): the receiver
    is τ^{≤b}, the sender σ^{≤a}. Links below the top frames are included, they are the steps that brought
    the lace into or out of the internal chains of the two labels."""
    parent, child, j = pair.parent, pair.child, pair.j
    steps: list[tuple[Lab, Lab]] = []
    for c in range(2, len(child) + 1):
        match prev_of(child, c):
            case (Up(), i) if 2 <= i <= len(parent) and next_of(parent, i) == (Down(j), c):
                steps.append((child.cut(c), parent.cut(i)))
            case _:
                pass
    for i in range(2, len(parent) + 1):
        match prev_of(parent, i):
            case (Down(j_), c) if j_ == j and 2 <= c <= len(child) and next_of(child, c) == (Up(), i):
                steps.append((parent.cut(i), child.cut(c)))
            case _:
                pass
    # both indices grow along the lace, so their sum orders the steps of the pair
    return sorted(steps, key=lambda step: len(step[0]) + len(step[1]), reverse=True)


@dataclass
class LabCHC:
    """The enumerated part of the knitted-trees and the Lab clauses built on it."""

    engine: LabEngine
    labels: list[Lab]
    pairs: list[Pair[Frame]]
    predicates: set[Lab] = field(default_factory=set[Lab])
    clauses: list[FNode] = field(default_factory=list[FNode])

    def predicate_symbols(self, function: ir.Function) -> list[FNode]:
        return [predicate(function, lab) for lab in sorted(self.predicates, key=lambda lab: lab.id)]


def build_lab(function: ir.Function, k: int, m: int, n: int) -> LabCHC:
    """Enumerates the labels and builds the Lab clauses, without queries.

    Only the final labels and pairs where both labels are non-continuous are kept."""
    engine = enumerate_labels(function, k, m, n)
    final_labels, final_pairs = engine.finals()
    lab = LabCHC(
        engine,
        labels=[lab for lab in final_labels if not engine.is_continuos(lab)],
        pairs=[p for p in final_pairs if not engine.is_continuos(p.parent) and not engine.is_continuos(p.child)],
    )

    # internal steps and facts: walk the prefixes of every label, a visited prefix has its own prefixes visited
    for label in lab.labels:
        for i in range(len(label), 0, -1):
            prefix = label.cut(i)
            if prefix in lab.predicates:
                break
            lab.predicates.add(prefix)
            if i == 1 or (i == 2 and is_initial(prefix)):
                lab.clauses.append(fact(function, prefix))
            elif prefix.prev is not None and prefix.prev[0] == Internal():
                lab.clauses.append(internal_clause(function, prefix))

    # external steps: walk the links of every pair, a visited step has the earlier steps of the pair visited
    visited_steps: set[tuple[Lab, Lab]] = set()
    for pair in lab.pairs:
        for receiver, sender in external_steps(pair):
            if (receiver, sender) in visited_steps:
                break
            visited_steps.add((receiver, sender))
            assert receiver.prefix is not None
            lab.predicates |= {receiver, receiver.prefix, sender}
            lab.clauses.append(external_clause(function, receiver, sender))

    return lab


def to_system(predicates: Iterable[FNode], clauses: Iterable[FNode]) -> CHCSystem:
    system = CHCSystem(logics.QF_UFLIA)
    for pred in predicates:
        system.add_predicate(pred)
    for clause in clauses:
        system.add_clause(clause)
    return system


def make_system(function: ir.Function, k: int, m: int, n: int, is_query: Callable[[Lab], bool]) -> CHCSystem:
    lab = build_lab(function, k, m, n)
    queries = [query(function, label) for label in lab.predicates if is_query(label)]
    return to_system(lab.predicate_symbols(function), [*lab.clauses, *queries])
