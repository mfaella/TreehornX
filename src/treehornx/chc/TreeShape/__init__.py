import itertools
from typing import Iterable

from treehornx import ir
from treehornx.chc.Lab.system import to_system
from treehornx.chc.sdta.SDTAContext import SDTAContext, true_ctx
from treehornx.chc.smt.sexpr import CHCSystem, Clause, Predicate
from treehornx.chc.TreeShape.system import TreeShapeCHC, build_tree_shape, enumerate_taints, tree_shape_from_lab
from treehornx.chc.TreeShape.TreeShapeRunner import TreeShapeRunner
from treehornx.feature_flags import FeatureFlags


def tree_shape_clauses(
    function: ir.Function,
    shape: TreeShapeCHC,
    m: int,
    n: int,
    ctx: SDTAContext | None,
) -> tuple[list[Predicate], Iterable[Clause]]:
    """Predicates and (lazily generated) clauses of a system that is unsat iff an input accepted by `ctx` leads to an
    output heap that is not a tree. The check assumes the memory safety checked by `pre.make_system`: the runs
    ending in a memory error are not in the system. Without `ctx` every input is accepted."""
    k = function.node.k
    runner = TreeShapeRunner(
        function,
        shape.pairs,
        ctx or true_ctx(),
        k,
        m,
        sym=shape.lab.sym,
        n=n,
        engine=shape.engine,
    )
    return runner.predicates(), itertools.chain(runner.clauses(), runner.queries())


def make_system(
    function: ir.Function,
    k: int,
    m: int,
    n: int,
    ctx: SDTAContext | None,
    flags: FeatureFlags,
) -> CHCSystem:
    """The system of `tree_shape_clauses`, enumerating the labels and their taints."""
    shape = build_tree_shape(function, k, m, n)
    return to_system(*tree_shape_clauses(function, shape, m, n, ctx), flags.clean_clause)


__all__ = [
    "TreeShapeCHC",
    "TreeShapeRunner",
    "build_tree_shape",
    "enumerate_taints",
    "make_system",
    "tree_shape_clauses",
    "tree_shape_from_lab",
]
