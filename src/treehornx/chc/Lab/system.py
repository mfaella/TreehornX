"""Compressed CHC system of the Lab encoding."""

from dataclasses import dataclass, field
from typing import Callable, Iterable

from pychc.chc_system import CHCSystem
from pysmt import logics
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.clauses import external_clause, fact, internal_clause, query
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.enum_models.core.Dir import Down, Internal, Up
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab import Frame, Lab, LabEngine, backbone_labels, initial_pairs, start_labels
from treehornx.enum_models.Lab.initial import is_initial


def enumerate_labels(function: ir.Function, k: int, m: int, n: int) -> LabEngine:
    assert k == function.node.k, f"k = {k} differs from the number of pointer fields {function.node.k}"
    engine = LabEngine(
        k,
        m,
        n=n,
        function=function,
    )
    engine.fix()
    return engine


def external_steps(pair: Pair[Lab]) -> list[tuple[Lab, Lab]]:
    """Every step between the two labels of the pair, as (receiver, sender) prefixes, from the latest one.

    A step is a link between a frame τ^b and the frame σ^a it follows in the lace (CHC IV/V): the receiver
    is τ^{≤b}, the sender σ^{≤a}. Links below the top frames are included, they are the steps that brought
    the lace into or out of the internal chains of the two labels."""
    parent, child, j = pair.parent, pair.child, pair.j
    steps: list[tuple[Lab, Lab]] = []
    for c in range(2, len(child) + 1):
        match child[c].prev:
            case (Up(), i) if 1 <= i <= len(parent):
                steps.append((child.cut(c), parent.cut(i)))
            case _:
                pass
    for i in range(2, len(parent) + 1):
        match parent[i].prev:
            case (Down(j_), c) if j_ == j and 1 <= c <= len(child):
                steps.append((parent.cut(i), child.cut(c)))
            case _:
                pass
    # both indices grow along the lace, so their sum orders the steps of the pair
    return sorted(steps, key=lambda step: len(step[0]) + len(step[1]), reverse=True)


@dataclass
class LabCHC:
    """The enumerated part of the knitted-trees and the Lab clauses built on it."""

    engine: LabEngine
    sym: ChcLabUtils
    labels: list[Lab]
    pairs: list[Pair[Lab]]
    predicates: set[Lab] = field(default_factory=set[Lab])
    clauses: list[FNode] = field(default_factory=list[FNode])

    def predicate_symbols(self) -> list[FNode]:
        return [self.sym.predicate(lab) for lab in sorted(self.predicates, key=self.sym.predicate_name)]


def build_lab(function: ir.Function, k: int, m: int, n: int) -> LabCHC:
    """Enumerates the labels and builds the Lab clauses, without queries.

    Only the final labels and pairs where both labels are non-continuous are kept."""
    engine = enumerate_labels(function, k, m, n)
    final_labels, final_pairs = engine.finals()
    lab = LabCHC(
        engine,
        ChcLabUtils(function, engine),
        labels=list(final_labels),
        pairs=list(final_pairs),
    )

    # internal steps and facts: walk the prefixes of every label, a visited prefix has its own prefixes visited
    for label in lab.labels:
        for i in range(len(label), 0, -1):
            prefix = label.cut(i)
            if prefix in lab.predicates:
                break
            lab.predicates.add(prefix)
            if i == 1 or (i == 2 and is_initial(prefix)):
                lab.clauses.append(fact(lab.sym, prefix))
            elif prefix.frame.prev is not None and prefix.frame.prev[0] == Internal():
                lab.clauses.append(internal_clause(lab.sym, prefix))

    # external steps: walk the links of every pair, a visited step has the earlier steps of the pair visited
    visited_steps: set[tuple[Lab, Lab, int]] = set()
    for pair in lab.pairs:
        for receiver, sender in external_steps(pair):
            if (receiver, sender, pair.j) in visited_steps:
                break
            visited_steps.add((receiver, sender, pair.j))
            assert receiver.prefix is not None
            lab.predicates |= {receiver, receiver.prefix, sender}
            lab.clauses.append(external_clause(lab.sym, receiver, sender, pair.j))

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
    queries = [query(lab.sym, label) for label in lab.predicates if is_query(label)]
    return to_system(lab.predicate_symbols(), [*lab.clauses, *queries])
