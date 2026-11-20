"""The result of the constant propagation (`MustConstantEngine`) on a label: the symbols equal to a constant in every
derivation leave the arguments and are replaced by the constant in the constraints, which are then simplified (the
constants fold, the conjuncts that become true are dropped: `make_non_trivial`)."""

from __future__ import annotations

from functools import cached_property
from typing import Mapping

from frozendict import frozendict
from typing_extensions import override

from treehornx import smt as sx
from treehornx.analysis.constraints import symbols as sy
from treehornx.smt.preprocess import make_non_trivial, simplify
from treehornx.analysis.constraints.symbols import Slot, Parent, Role
from treehornx.analysis.commons.ConstrTLab import ConstrTLab


class ConstConstrTLab(ConstrTLab):
    def __init__(self, label: ConstrTLab, consts: Mapping[sy.Symbol, sx.Constant]) -> None:
        """`consts`: the symbols of `label` equal to a constant in every derivation of it."""
        super().__init__(label.tlab, label.builder)
        self.label = label
        self.consts: frozendict[sy.Symbol, sx.Constant] = frozendict(consts)

    @override
    def key(self) -> tuple[object, ...]:
        return (self.label, self.consts)

    def mapping(self, role: Role | None) -> dict[sx.Var, sx.SExpr]:
        return {s.with_role(role): c for s, c in self.consts.items()}

    @cached_property
    def _symbols(self) -> tuple[sy.Symbol, ...]:
        return tuple(s for s in self.label.symbols() if s not in self.consts)

    @cached_property
    def _args(self) -> tuple[sy.Symbol, ...]:
        return tuple(s for s in self.label.args() if s not in self.consts)

    @override
    def symbols(self, role: Role | None = None) -> list[sy.Symbol]:
        return [s.with_role(role) for s in self._symbols]

    @override
    def args(self, role: Role | None = None) -> list[sy.Symbol]:
        return [s.with_role(role) for s in self._args]

    @override
    def constraints(self, role: Role | None = None) -> list[sx.SExpr]:
        mapping = self.mapping(role)
        return make_non_trivial(c.substitute(mapping) for c in self.label.constraints(role))

    @override
    def consistency(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        assert isinstance(child, ConstConstrTLab), "parent and child built by different phases"
        mapping = {**self.mapping(Parent()), **child.mapping(Slot(j))}
        return make_non_trivial(c.substitute(mapping) for c in self.label.consistency(child.label, j))

    @override
    def error_constraints(self, n: int, role: Role | None = None) -> list[sx.SExpr]:
        mapping = self.mapping(role)
        return make_non_trivial(c.substitute(mapping) for c in self.label.error_constraints(n, role))

    @override
    def edge_error(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        assert isinstance(child, ConstConstrTLab), "parent and child built by different phases"
        mapping = {**self.mapping(Parent()), **child.mapping(Slot(j))}
        return make_non_trivial(c.substitute(mapping) for c in self.label.edge_error(child.label, j))

    @override
    def rename(self, expr: sx.SExpr, role: Role | None = None) -> sx.SExpr:
        return simplify(self.label.rename(expr, role).substitute(self.mapping(role)))
