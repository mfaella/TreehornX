"""The result of the equality must analysis (`MustEqualityEngine`) on a label: the symbols of a class leave the
arguments and are replaced by a new symbol of the class (`I<k>` for Int, `B<k>` for Bool, `symbol_generator`) in the
constraints, which then lose their trivial conjuncts (`make_non_trivial`). The new symbol takes the place of the first
symbol of the class in the arguments."""

from __future__ import annotations

from functools import cached_property
from typing import Iterable

from frozendict import frozendict
from typing_extensions import override

from treehornx import smt as sx
from treehornx.analysis.constraints import symbols as sy
from treehornx.smt.preprocess import make_non_trivial, simplify
from treehornx.analysis.constraints.symbols import Slot, Parent, Role
from treehornx.analysis.commons import symbol_generator
from treehornx.analysis.commons.ConstrTLab import ConstrTLab


class EqConstrTLab(ConstrTLab):
    def __init__(self, label: ConstrTLab, classes: Iterable[set[sy.Symbol]]) -> None:
        """`classes`: disjoint sets of symbols of `label` equal in every derivation of it. The symbols that are not
        arguments of `label` are ignored; a symbol in no class is alone in its class. The new names skip every symbol
        of `label` (`symbols()`), so they never clash with a quantified symbol either."""
        super().__init__(label.tlab, label.builder)
        self.label = label
        args = label.args()
        position = {s: i for i, s in enumerate(args)}
        taken = set(label.symbols())
        merged = sorted(
            (sorted((s for s in cls if s in position), key=position.__getitem__) for cls in classes),
            key=lambda members: position[members[0]] if members else len(position),
        )
        merged = [members for members in merged if len(members) > 1]
        fresh = {
            type_: (s for s in symbol_generator(len(taken) + len(merged), type_) if s not in taken)
            for type_ in (sx.Type.Int, sx.Type.Bool)
        }
        reps: dict[sy.Symbol, sy.Symbol] = {}
        new: dict[sy.Symbol, sy.Symbol] = {}
        for members in merged:
            symbol = next(fresh[members[0].type])
            new[members[0]] = symbol
            for s in members:
                reps[s] = symbol
        self.reps: frozendict[sy.Symbol, sy.Symbol] = frozendict(sorted(reps.items(), key=lambda kv: position[kv[0]]))
        """Every symbol that leaves the arguments, with the new symbol of its class."""
        self._new: frozendict[sy.Symbol, sy.Symbol] = frozendict(new)
        """The first symbol of each class → the new symbol that takes its place in the arguments."""

    @override
    def key(self) -> tuple[object, ...]:
        return (self.label, self.reps)

    def mapping(self, role: Role | None) -> dict[sx.Var, sx.SExpr]:
        return {s.with_role(role): rep.with_role(role) for s, rep in self.reps.items()}

    def _replace(self, symbols: Iterable[sy.Symbol]) -> tuple[sy.Symbol, ...]:
        """`symbols` with the first symbol of each class replaced by the new symbol and the others removed."""
        return tuple(self._new.get(s, s) for s in symbols if s in self._new or s not in self.reps)

    @cached_property
    def _symbols(self) -> tuple[sy.Symbol, ...]:
        return self._replace(self.label.symbols())

    @cached_property
    def _args(self) -> tuple[sy.Symbol, ...]:
        return self._replace(self.label.args())

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
        assert isinstance(child, EqConstrTLab), "parent and child built by different phases"
        mapping = {**self.mapping(Parent()), **child.mapping(Slot(j))}
        return make_non_trivial(c.substitute(mapping) for c in self.label.consistency(child.label, j))

    @override
    def error_constraints(self, n: int, role: Role | None = None) -> list[sx.SExpr]:
        mapping = self.mapping(role)
        return make_non_trivial(c.substitute(mapping) for c in self.label.error_constraints(n, role))

    @override
    def edge_error(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        assert isinstance(child, EqConstrTLab), "parent and child built by different phases"
        mapping = {**self.mapping(Parent()), **child.mapping(Slot(j))}
        return make_non_trivial(c.substitute(mapping) for c in self.label.edge_error(child.label, j))

    @override
    def rename(self, expr: sx.SExpr, role: Role | None = None) -> sx.SExpr:
        return simplify(self.label.rename(expr, role).substitute(self.mapping(role)))
