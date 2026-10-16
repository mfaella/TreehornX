"""CHC system checking the output heap: tree shape and, optionally, a postcondition."""

from typing import Any, cast

from pychc.chc_system import CHCSystem
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.symbols import predicate as lab_predicate
from treehornx.chc.Lab.system import build_lab, external_steps, to_system
from treehornx.chc.post.clauses import (
    empty_output_query,
    external_clause,
    fact,
    internal_clause,
    is_overflow,
    is_violation,
    query,
)
from treehornx.chc.post.hoare import PostUnderPreRunner
from treehornx.chc.post.symbols import dfs_predicate
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.Dfs import Dfs, DfsEngine, clean_end, dfs_initial, sigma_of
from treehornx.enum_models.Lab import Lab


def make_system(
    function: ir.Function,
    k: int,
    m: int,
    n: int,
    n_dfs: int,
    ctx: SDTAContext | None = None,
    accept_nil: bool = False,
    check_overflow: bool = True,
    pre: SDTAContext | None = None,
) -> CHCSystem:
    """Unsat iff some execution ending at `exit` produces an output heap that is not a tree or, when `ctx` (the
    negation of the postcondition) is given, a tree accepted by `ctx`.

    `accept_nil` is ψ_F(nil) of `ctx`, the acceptance of the empty output tree. With `check_overflow` the
    system is also unsat when some DFS label exceeds the bound `n_dfs`, as the label overflow of Lab: the visit
    did not fit in the bound, so its result is unknown.

    With `pre`, only the executions whose input tree is accepted by the precondition are checked: the
    violations are collected bottom-up by the precondition automaton (`PostUnderPreRunner`), whose root query
    replaces the direct ones."""
    lab = build_lab(function, k, m, n)
    starts, initial_pairs = dfs_initial(function, lab.pairs)
    engine = DfsEngine(k, m, n_dfs, initial_pairs=initial_pairs, start_labels=starts, function=function)
    engine.fix()

    final_labels, final_pairs = engine.finals()
    labels = [rho for rho in final_labels if not engine.is_continuos(rho)]
    pairs = [p for p in final_pairs if not engine.is_continuos(p.parent) and not engine.is_continuos(p.child)]

    predicates: set[Dfs] = set()
    lab_labels: set[Lab] = set(lab.predicates)
    clauses: list[FNode] = []

    # facts and internal steps: walk the prefixes of every label, a visited prefix has its own prefixes visited
    for label in labels:
        for i in range(len(label), 0, -1):
            prefix = label.cut(i)
            if prefix in predicates:
                break
            predicates.add(prefix)
            if i == 1:
                lab_labels.add(sigma_of(prefix))
                clauses.append(fact(function, ctx, prefix))
            elif prefix.prev is not None and prefix.prev[0] == Internal():
                clauses.append(internal_clause(function, ctx, prefix))

    # steps between nodes: walk the links of every pair, a visited step has the earlier steps of the pair visited
    visited_steps: set[tuple[Dfs, Dfs]] = set()
    for pair in pairs:
        for receiver, sender in cast(list[tuple[Dfs, Dfs]], external_steps(cast(Any, pair))):
            if (receiver, sender) in visited_steps:
                break
            visited_steps.add((receiver, sender))
            assert receiver.prefix is not None
            predicates |= {receiver, receiver.prefix, sender}
            clauses.append(external_clause(function, ctx, receiver, sender))

    if pre is not None:
        runner = PostUnderPreRunner(
            function, pairs, pre, k, m, post=ctx, n_dfs=n_dfs, accept_nil=accept_nil, check_overflow=check_overflow
        )
        return to_system(
            [
                *(lab_predicate(function, sigma) for sigma in sorted(lab_labels, key=lambda lab: lab.id)),
                *(dfs_predicate(function, ctx, rho) for rho in sorted(predicates, key=lambda rho: rho.id)),
                *runner.predicates(),
            ],
            [*lab.clauses, *clauses, *runner.clauses(), *runner.queries()],
        )

    queries = [
        query(function, ctx, rho)
        for rho in predicates
        if is_violation(ctx, rho) or (check_overflow and is_overflow(n_dfs, rho))
    ]
    if ctx is not None and accept_nil:
        root = function.ROOT
        queries.extend(
            empty_output_query(function, sigma)
            for sigma in lab_labels
            if clean_end(function, sigma) and sigma.frame.isnil[root]
        )

    return to_system(
        [
            *(lab_predicate(function, sigma) for sigma in sorted(lab_labels, key=lambda lab: lab.id)),
            *(dfs_predicate(function, ctx, rho) for rho in sorted(predicates, key=lambda rho: rho.id)),
        ],
        [*lab.clauses, *clauses, *queries],
    )
