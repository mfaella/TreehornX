import itertools
from typing import Iterable

from treehornx import ir
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.system import to_system
from treehornx.chc.Post.system import PostCHC, build_post, enumerate_taints, post_from_lab
from treehornx.chc.Post.TreeShapeRunner import TreeShapeRunner
from treehornx.chc.sdta.SDTAContext import SDTAContext, true_ctx
from treehornx.chc.smt.sexpr import CHCSystem, Clause, Predicate
from treehornx.feature_flags import FeatureFlags


def tree_shape_clauses(
    function: ir.Function,
    post: PostCHC,
    m: int,
    n: int,
    ctx: SDTAContext | None,
    exit_codes: frozenset[ExitCodeKind] = frozenset(),
) -> tuple[list[Predicate], Iterable[Clause]]:
    """Predicates and (lazily generated) clauses of a system that is unsat iff an input accepted by `ctx` leads to an
    output heap that is not a tree, or to an exit status in `exit_codes` (none by default: the tree-shape check
    assumes the memory safety checked by `pre.make_system`). Without `ctx` every input is accepted."""
    k = function.node.k
    runner = TreeShapeRunner(
        function, post.pairs, ctx or true_ctx(), k, m, sym=post.lab.sym, n=n, engine=post.engine, exit_codes=exit_codes
    )
    return runner.predicates(), itertools.chain(runner.clauses(), runner.queries())


def make_system(
    function: ir.Function,
    k: int,
    m: int,
    n: int,
    ctx: SDTAContext | None,
    flags: FeatureFlags,
    exit_codes: frozenset[ExitCodeKind] = frozenset(),
) -> CHCSystem:
    """The system of `tree_shape_clauses`, enumerating the labels and their taints."""
    post = build_post(function, k, m, n)
    return to_system(*tree_shape_clauses(function, post, m, n, ctx, exit_codes), flags.clean_clause)


__all__ = [
    "PostCHC",
    "TreeShapeRunner",
    "build_post",
    "enumerate_taints",
    "make_system",
    "post_from_lab",
    "tree_shape_clauses",
]
