"""Must analysis of the constants (`var = const`) on `MustEngine`.

A fact is a `ConstFacts`: the dictionary `consts` (variable → constant) and the equalities `eqs` between variables (a
`networkx.utils.UnionFind`, `treehornx.utils.union_find`).
The equalities are needed to move a constant from one variable to another (across an edge, `p_x = c0_y`, or inside a
label); the result of the analysis is `consts`.

A `ConstFacts` is closed: when a variable of a class of `eqs` has a constant, every variable of the class has it.
`meet` (conjunction) merges the equalities and the constants, then closes them; two different constants in one class
are a clash, and `meet` returns `BOTTOM`. `join` (common facts) keeps a constant only when every alternative gives the
same one, and the equalities common to all alternatives.

The facts of a label are the `var = const`, `var = var`, `b` and `not b` (Bool) conjuncts of its constraints, its
quantified symbols included, projected onto its arguments; the facts of an edge are those of its consistency
constraints. A label whose own constants clash has no derivation: its facts are `BOTTOM`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable, Mapping

from frozendict import frozendict
from typing_extensions import override

from treehornx import smt as sx
from treehornx.analysis.abstract_interpretation.ConstConstrTLab import ConstConstrTLab
from treehornx.analysis.abstract_interpretation.MustEngine import BOTTOM, Bottom, MustEngine
from treehornx.analysis.abstract_interpretation.MustEqualityEngine import EQUALITY_ARITY, rename_role, var_equalities
from treehornx.analysis.commons.ConstrTLab import ConstrTLab
from treehornx.analysis.constraints.symbols import Role, Symbol
from treehornx.symbolic_tree import Edge
from treehornx.smt.preprocess import conjuncts
from treehornx.utils import union_find as uf
from treehornx.utils.union_find import UnionFind


@dataclass(frozen=True, eq=False)
class ConstFacts:
    consts: frozendict[sx.Var, sx.Constant]
    """variable → its constant."""
    eqs: UnionFind[sx.Var]
    """The equalities between variables (to move the constants). Never modified after construction."""

    @staticmethod
    def make(consts: Iterable[tuple[sx.Var, sx.Constant]], eqs: UnionFind[sx.Var]) -> ConstFacts | Bottom:
        """The closed facts of `consts` and `eqs`; `BOTTOM` when two different constants meet in one class (or on one
        variable)."""
        by_root: dict[sx.Var, sx.Constant] = {}
        for v, c in consts:
            old = by_root.setdefault(uf.root(eqs, v), c)
            if old is not c:  # constants are interned: identity is equality
                return BOTTOM
        closed: dict[sx.Var, sx.Constant] = {}
        for cls in eqs.to_sets():
            r = uf.root(eqs, next(iter(cls)))
            if r in by_root:
                closed.update((v, by_root[r]) for v in cls)
        # the variables in no class are their own root
        closed.update((v, c) for v, c in by_root.items() if v not in eqs.parents)
        return ConstFacts(frozendict(closed), eqs)

    @staticmethod
    def empty() -> ConstFacts:
        return ConstFacts(frozendict(), UnionFind())

    @cached_property
    def _partition(self) -> frozenset[frozenset[sx.Var]]:
        return uf.partition(self.eqs)

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, ConstFacts) and self.consts == other.consts and self._partition == other._partition

    @override
    def __hash__(self) -> int:
        return hash((self.consts, self._partition))

    @override
    def __repr__(self) -> str:
        consts = ", ".join(f"{v.name}={c.to_smt()}" for v, c in sorted(self.consts.items(), key=lambda kv: kv[0].name))
        classes = ", ".join(sorted("{" + ", ".join(sorted(v.name for v in cls)) + "}" for cls in self._partition))
        return f"ConstFacts({{{consts}}}, [{classes}])"


def const_facts(constraints: Iterable[sx.SExpr]) -> list[tuple[sx.Var, sx.Constant]]:
    """The `var = const`, `b` and `not b` conjuncts of `constraints`."""
    result: list[tuple[sx.Var, sx.Constant]] = []
    for constraint in constraints:
        for c in conjuncts(constraint):
            if isinstance(c, sx.Var) and c.type is sx.Type.Bool:
                result.append((c, sx.TRUE))
            elif isinstance(c, sx.OpExpr) and c.op is sx.Operator.NOT and isinstance(c.args[0], sx.Var):
                result.append((c.args[0], sx.FALSE))
            elif isinstance(c, sx.OpExpr) and c.op is sx.Operator.EQ and len(c.args) == EQUALITY_ARITY:
                a, b = c.args
                if isinstance(a, sx.Var) and isinstance(b, sx.Constant):
                    result.append((a, b))
                elif isinstance(b, sx.Var) and isinstance(a, sx.Constant):
                    result.append((b, a))
    return result


@dataclass
class MustConstantEngine(MustEngine[ConstFacts]):
    _label_cache: dict[tuple[ConstrTLab, Role | None], ConstFacts | Bottom] = field(
        init=False, default_factory=dict[tuple[ConstrTLab, Role | None], ConstFacts | Bottom]
    )
    _edge_cache: dict[Edge[ConstrTLab], ConstFacts | Bottom] = field(
        init=False, default_factory=dict[Edge[ConstrTLab], ConstFacts | Bottom]
    )

    @override
    def meet(self, *ds: ConstFacts) -> ConstFacts | Bottom:
        eqs = uf.join(*(d.eqs for d in ds))
        return ConstFacts.make((kv for d in ds for kv in d.consts.items()), eqs)

    @override
    def join(self, *ds: ConstFacts) -> ConstFacts:
        first, rest = ds[0], ds[1:]
        consts = {v: c for v, c in first.consts.items() if all(d.consts.get(v) is c for d in rest)}
        # the inputs are closed, so the common constants and the common equalities are closed too
        return ConstFacts(frozendict(consts), uf.meet(*(d.eqs for d in ds)))

    @override
    def project(self, f: ConstFacts, variables: Iterable[sx.Var]) -> ConstFacts:
        keep = set(variables)
        return ConstFacts(frozendict({v: c for v, c in f.consts.items() if v in keep}), uf.restrict(f.eqs, keep))

    @override
    def with_role(self, facts: ConstFacts, role: Role | None) -> ConstFacts:
        return ConstFacts(
            frozendict({rename_role(v, role): c for v, c in facts.consts.items()}),
            uf.transform(facts.eqs, lambda v: rename_role(v, role)),
        )

    def _facts(self, constraints: list[sx.SExpr]) -> ConstFacts | Bottom:
        return ConstFacts.make(const_facts(constraints), uf.of(var_equalities(constraints)))

    @override
    def label_facts(self, lab: ConstrTLab, role: Role | None = None) -> ConstFacts | Bottom:
        key = (lab, role)
        if key not in self._label_cache:
            facts = self._facts(lab.constraints(role))
            self._label_cache[key] = facts if isinstance(facts, Bottom) else self.project(facts, lab.args(role))
        return self._label_cache[key]

    @override
    def edge_facts(self, e: Edge[ConstrTLab]) -> ConstFacts | Bottom:
        if e not in self._edge_cache:
            self._edge_cache[e] = self._facts(ConstrTLab.consistency_constraints(e.parent, e.child, e.j))
        return self._edge_cache[e]

    @override
    def apply(self, s: ConstrTLab, d: ConstFacts) -> ConstrTLab:
        consts: Mapping[Symbol, sx.Constant] = {v: c for v, c in d.consts.items() if isinstance(v, Symbol)}
        return ConstConstrTLab(s, consts)

    @override
    def no_facts(self) -> ConstFacts:
        return ConstFacts.empty()
