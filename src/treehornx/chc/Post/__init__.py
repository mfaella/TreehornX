import itertools
from typing import Iterable

from treehornx import ir
from treehornx.chc.Lab.system import to_system
from treehornx.chc.Post.PostRunner import PostRunner
from treehornx.chc.Post.symbols import PostSymbols
from treehornx.chc.sdta.SDTAContext import SDTAContext, true_ctx
from treehornx.chc.smt.sexpr import CHCSystem, Clause, Predicate
from treehornx.chc.TreeShape.system import TreeShapeCHC, build_tree_shape
from treehornx.feature_flags import FeatureFlags


def post_clauses(
    function: ir.Function,
    shape: TreeShapeCHC,
    m: int,
    n: int,
    ctx: SDTAContext | None,
    post: SDTAContext,
) -> tuple[list[Predicate], Iterable[Clause]]:
    """Predicates and (lazily generated) clauses of a system that is unsat iff an input accepted by `ctx` leads to an
    output tree accepted by the negated postcondition `post`. The check assumes memory safety (the runs ending in a
    memory error are not in the system) and that the output heap is a tree (checked by `TreeShape.make_system`).
    Without `ctx` every input is accepted."""
    k = function.node.k
    runner = PostRunner(
        function,
        shape.pairs,
        ctx or true_ctx(),
        k,
        m,
        sym=shape.lab.sym,
        n=n,
        engine=shape.engine,
        post=post,
    )
    return runner.predicates(), itertools.chain(runner.clauses(), runner.queries())


def make_system(
    function: ir.Function,
    k: int,
    m: int,
    n: int,
    ctx: SDTAContext | None,
    post: SDTAContext,
    flags: FeatureFlags,
) -> CHCSystem:
    """The system of `post_clauses`, enumerating the labels and their taints."""
    shape = build_tree_shape(function, k, m, n)
    return to_system(*post_clauses(function, shape, m, n, ctx, post), flags.clean_clause)


__all__ = ["PostRunner", "PostSymbols", "make_system", "post_clauses"]
