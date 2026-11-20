"""Must analysis of the equalities between variables (`var = var`) on `MustEngine`.

A fact is a `networkx.utils.UnionFind` (`treehornx.utils.union_find`): the classes of variables that are equal. The
engine's `meet` (conjunction) is `union_find.join` (the union of the classes), the engine's `join` (common facts) is
`union_find.meet` (two variables stay together only when every alternative does): the module names the operations by
the order on facts, the engine by the order on concrete states. `project` cuts the classes. A conjunction of
equalities between variables is always satisfiable, so `meet` never returns `BOTTOM`.

The facts of a label are the `var = var` conjuncts of its constraints, its quantified symbols included, projected
onto its arguments; the facts of an edge are those of its consistency constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from typing_extensions import override

from treehornx import smt as sx
from treehornx.analysis.abstract_interpretation.EqConstrTLab import EqConstrTLab
from treehornx.analysis.abstract_interpretation.MustEngine import Bottom, MustEngine
from treehornx.analysis.commons.ConstrTLab import ConstrTLab
from treehornx.analysis.constraints.symbols import Role, Symbol
from treehornx.symbolic_tree import Edge
from treehornx.smt.preprocess import conjuncts
from treehornx.utils import union_find as uf
from treehornx.utils.union_find import UnionFind

EQUALITY_ARITY = 2

if TYPE_CHECKING:
    VarUnionFind = UnionFind[sx.Var]
else:  # nx.utils.UnionFind is not subscriptable at runtime
    VarUnionFind = UnionFind


def var_equalities(constraints: Iterable[sx.SExpr]) -> list[tuple[sx.Var, sx.Var]]:
    """The `var = var` conjuncts of `constraints`."""
    pairs: list[tuple[sx.Var, sx.Var]] = []
    for constraint in constraints:
        for c in conjuncts(constraint):
            if isinstance(c, sx.OpExpr) and c.op is sx.Operator.EQ and len(c.args) == EQUALITY_ARITY:
                a, b = c.args
                if isinstance(a, sx.Var) and isinstance(b, sx.Var):
                    pairs.append((a, b))
    return pairs


def rename_role(v: sx.Var, role: Role | None) -> sx.Var:
    assert isinstance(v, Symbol), f"{v} is not a symbol of a label"
    return v.with_role(role)


def symbol_classes(facts: UnionFind[sx.Var]) -> list[set[Symbol]]:
    """The classes of `facts` (at least two members), as the sets of symbols `EqConstrTLab` reads."""
    return [{v for v in cls if isinstance(v, Symbol)} for cls in uf.partition(facts)]


@dataclass
class MustEqualityEngine(MustEngine[VarUnionFind]):
    _label_cache: dict[tuple[ConstrTLab, Role | None], VarUnionFind] = field(
        init=False, default_factory=dict[tuple[ConstrTLab, Role | None], VarUnionFind]
    )
    _edge_cache: dict[Edge[ConstrTLab], VarUnionFind] = field(
        init=False, default_factory=dict[Edge[ConstrTLab], VarUnionFind]
    )

    @override
    def meet(self, *ds: UnionFind[sx.Var]) -> UnionFind[sx.Var] | Bottom:
        return uf.join(*ds)

    @override
    def join(self, *ds: UnionFind[sx.Var]) -> UnionFind[sx.Var]:
        return uf.meet(*ds)

    @override
    def project(self, f: UnionFind[sx.Var], variables: Iterable[sx.Var]) -> UnionFind[sx.Var]:
        return uf.restrict(f, variables)

    @override
    def with_role(self, facts: UnionFind[sx.Var], role: Role | None) -> UnionFind[sx.Var]:
        return uf.transform(facts, lambda v: rename_role(v, role))

    @override
    def equal(self, a: UnionFind[sx.Var], b: UnionFind[sx.Var]) -> bool:
        return uf.equal(a, b)

    @override
    def label_facts(self, lab: ConstrTLab, role: Role | None = None) -> UnionFind[sx.Var]:
        key = (lab, role)
        if key not in self._label_cache:
            self._label_cache[key] = uf.restrict(uf.of(var_equalities(lab.constraints(role))), lab.args(role))
        return self._label_cache[key]

    @override
    def edge_facts(self, e: Edge[ConstrTLab]) -> UnionFind[sx.Var]:
        if e not in self._edge_cache:
            self._edge_cache[e] = uf.of(var_equalities(ConstrTLab.consistency_constraints(e.parent, e.child, e.j)))
        return self._edge_cache[e]

    @override
    def apply(self, s: ConstrTLab, d: UnionFind[sx.Var]) -> ConstrTLab:
        return EqConstrTLab(s, symbol_classes(d))

    @override
    def no_facts(self) -> UnionFind[sx.Var]:
        return uf.of(())
