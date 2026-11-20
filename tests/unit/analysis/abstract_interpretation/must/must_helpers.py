"""Helpers of the must-analysis tests: `FakeLabel`, a label built by hand, and `sym`/`eq` to write its constraints.

When the real `treehornx.analysis.commons.ConstrTLab` cannot be imported (during the refactor, `enum_models/frame.py`
and other modules are missing), this module installs a stub of it with the same interface (identity, `symbols`,
`args`, `constraints`, `consistency_constraints`) before the engines are imported. `conftest.py` imports it first.
"""

from __future__ import annotations

import sys
import types
from functools import cached_property
from typing import Iterable

from treehornx import smt as sx
from treehornx.analysis.constraints.symbols import Parent, Role, Slot, Symbol


try:
    from treehornx.analysis.commons.ConstrTLab import ConstrTLab
except ImportError:

    class ConstrTLab:
        def __init__(self, tlab: object, builder: object) -> None:
            self.tlab = tlab
            self.builder = builder

        def key(self) -> tuple[object, ...]:
            return (self.tlab,)

        @cached_property
        def _hash(self) -> int:
            return hash((type(self), self.key()))

        def __hash__(self) -> int:
            return self._hash

        def __eq__(self, other: object) -> bool:
            if self is other:
                return True
            if type(other) is not type(self):
                return False
            assert isinstance(other, ConstrTLab)
            return self.key() == other.key()

        def symbols(self, role: Role | None = None) -> list[Symbol]:
            raise NotImplementedError

        def args(self, role: Role | None = None) -> list[Symbol]:
            raise NotImplementedError

        def constraints(self, role: Role | None = None) -> list[sx.SExpr]:
            raise NotImplementedError

        def rename(self, expr: sx.SExpr, role: Role | None = None) -> sx.SExpr:
            return expr

        @staticmethod
        def consistency_constraints(parent: ConstrTLab, child: ConstrTLab, j: int) -> list[sx.SExpr]:
            return parent.consistency(child, j)

        def consistency(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
            raise NotImplementedError

    _stub = types.ModuleType("treehornx.analysis.commons.ConstrTLab")
    _stub.ConstrTLab = ConstrTLab  # type: ignore[attr-defined]
    sys.modules["treehornx.analysis.commons.ConstrTLab"] = _stub


# ----------------------------------------------------------------------------- helpers for the tests


def sym(name: str, role: Role | None = None) -> Symbol:
    """A symbol; the names starting with `b` are Bool, the others Int."""
    type_ = sx.Type.Bool if name.startswith("b") else sx.Type.Int
    return Symbol.make(base_name=name, type=type_, role=role)


def eq(a: sx.SExpr | int | bool, b: sx.SExpr | int | bool) -> sx.SExpr:
    return sx.OpExpr.make(op=sx.Operator.EQ, args=(a, b))


def _with_role(expr: sx.SExpr, role: Role | None) -> sx.SExpr:
    mapping: dict[sx.Var, sx.SExpr] = {
        v: v.with_role(role) for v in set(expr.free_variables()) if isinstance(v, Symbol)
    }
    return expr.substitute(mapping)


class FakeLabel(ConstrTLab):
    """A label named `name` with the arguments `args` and the constraints `cons`, both on the bare symbols (`sym(n)`);
    the constraints may use symbols that are not arguments (quantified): `symbols()` gives them after the arguments.
    `links[(child, j)]` are the pairs
    (parent symbol, child symbol) equal on the edge to the j-th child `child` (a name), `extra[(child, j)]` more
    constraints of the edge, on the symbols with the roles `Parent()` and `Slot(j)`."""

    def __init__(
        self,
        name: str,
        args: Iterable[str],
        cons: Iterable[sx.SExpr] = (),
        links: dict[tuple[str, int], list[tuple[str, str]]] | None = None,
        extra: dict[tuple[str, int], list[sx.SExpr]] | None = None,
    ) -> None:
        super().__init__(name, None)
        self.name = name
        self._args = tuple(sym(a) for a in args)
        quantified = {v for c in self.cons for v in c.free_variables() if isinstance(v, Symbol)} - set(self._args)
        self._symbols = self._args + tuple(sorted(quantified, key=lambda v: v.name))
        self.cons = list(cons)
        self.links = links or {}
        self.extra = extra or {}

    def __repr__(self) -> str:
        return f"FakeLabel({self.name})"

    def symbols(self, role: Role | None = None) -> list[Symbol]:
        """The arguments, then the quantified symbols of the constraints (in name order)."""
        return [s.with_role(role) for s in self._symbols]

    def args(self, role: Role | None = None) -> list[Symbol]:
        return [s.with_role(role) for s in self._args]

    def constraints(self, role: Role | None = None) -> list[sx.SExpr]:
        return [_with_role(c, role) for c in self.cons]

    def consistency(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        assert isinstance(child, FakeLabel)
        pairs = self.links.get((child.name, j), [])
        return [eq(sym(a, Parent()), sym(b, Slot(j))) for a, b in pairs] + self.extra.get((child.name, j), [])
