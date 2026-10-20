"""Compressed CHC system of the Lab encoding."""

from dataclasses import dataclass, field
from typing import Callable, Iterable

from pychc.chc_system import CHCSystem
from pysmt import logics
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.clauses import external_clause, fact, internal_clause, query
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab import Frame, Lab, LabEngine, backbone_labels, initial_pairs, start_labels
from treehornx.enum_models.Lab.helpers import down_links, up_links
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
    the lace into or out of the internal chains of the two labels.

    The receiver is given by the kind of link, not by the frames: a child frame entered from the parent and
    leaving to it (e.g. a new node linked by its parent) has prev = Up but sends the lace in its up-link."""
    parent, child, j = pair.parent, pair.child, pair.j
    steps: list[tuple[Lab, Lab]] = [(child.cut(c), parent.cut(i)) for i, c in down_links(parent, child, j)]
    steps += [(parent.cut(i), child.cut(c)) for i, c in up_links(parent, child, j)]
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

    def add_clause(self, clause: FNode | None) -> None:
        """Adds `clause`, unless the clean phase found its body unsatisfiable."""
        if clause is not None:
            self.clauses.append(clause)

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
                lab.add_clause(fact(lab.sym, prefix))
            elif prefix.frame.prev == Internal():
                lab.add_clause(internal_clause(lab.sym, prefix))

    # external steps: walk the links of every pair, a visited step has the earlier steps of the pair visited
    visited_steps: set[tuple[Lab, Lab, int]] = set()
    for pair in lab.pairs:
        for receiver, sender in external_steps(pair):
            if (receiver, sender, pair.j) in visited_steps:
                break
            visited_steps.add((receiver, sender, pair.j))
            assert receiver.prefix is not None
            lab.predicates |= {receiver, receiver.prefix, sender}
            lab.add_clause(external_clause(lab.sym, receiver, sender, pair.j))

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
    queries = [q for label in lab.predicates if is_query(label) and (q := query(lab.sym, label)) is not None]
    return to_system(lab.predicate_symbols(), [*lab.clauses, *queries])
