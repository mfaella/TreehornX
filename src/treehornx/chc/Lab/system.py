"""Compressed CHC system of the Lab encoding."""

from typing import Callable

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


def make_system(function: ir.Function, k: int, m: int, n: int, is_query: Callable[[Lab], bool]) -> CHCSystem:
    engine = enumerate_labels(function, k, m, n)
    final_labels, final_pairs = engine.finals()
    labels = [lab for lab in final_labels if not engine.is_continuos(lab)]
    pairs = [p for p in final_pairs if not engine.is_continuos(p.parent) and not engine.is_continuos(p.child)]

    predicates: set[Lab] = set()
    clauses: list[FNode] = []

    # internal steps and facts: walk the prefixes of every label, a visited prefix has its own prefixes visited
    for lab in labels:
        for i in range(len(lab), 0, -1):
            prefix = lab.cut(i)
            if prefix in predicates:
                break
            predicates.add(prefix)
            if i == 1 or (i == 2 and is_initial(prefix)):
                clauses.append(fact(function, prefix))
            elif prefix.prev is not None and prefix.prev[0] == Internal():
                clauses.append(internal_clause(function, prefix))

    # external steps: walk the links of every pair, a visited step has the earlier steps of the pair visited
    visited_steps: set[tuple[Lab, Lab]] = set()
    for pair in pairs:
        for receiver, sender in external_steps(pair):
            if (receiver, sender) in visited_steps:
                break
            visited_steps.add((receiver, sender))
            assert receiver.prefix is not None
            predicates |= {receiver, receiver.prefix, sender}
            clauses.append(external_clause(function, receiver, sender))

    clauses.extend(query(function, lab) for lab in predicates if is_query(lab))

    system = CHCSystem(logics.QF_UFLIA)
    for lab in sorted(predicates, key=lambda lab: lab.id):
        system.add_predicate(predicate(function, lab))
    for clause in clauses:
        system.add_clause(clause)
    return system
