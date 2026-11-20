"""Quantifier-free SMT-LIB2 terms over integers and booleans.

Terms are immutable and interned (`treehornx.intern`): `X.make(...)` returns the instance of a term already alive,
so equality and hashing are by identity. The package has no predicates and no quantifiers: the CHC layer
(`chc/smt/sexpr.py`) builds predicate applications and clauses on top of these terms.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping, Union

from typing_extensions import override

from treehornx.intern import intern


class Operator(Enum):
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "div"
    MOD = "mod"
    AND = "and"
    OR = "or"
    NOT = "not"
    IMPLIES = "=>"
    EQ = "="
    ITE = "ite"
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="


ARITHMETIC_OPS = frozenset({Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV, Operator.MOD})


class Type(Enum):
    Int = "Int"
    Bool = "Bool"


@dataclass(slots=True, frozen=True, eq=False, init=False, weakref_slot=True)
class SMTNode(ABC):
    @abstractmethod
    def to_smt(self) -> str:
        """Return the SMT-LIB representation of the node."""
        ...

    @abstractmethod
    def free_variables(self) -> Iterator[Var]:
        """Return the free variables in the node, with repetitions."""
        ...


@dataclass(slots=True, frozen=True, eq=False, init=False)
class SExpr(SMTNode, ABC):
    @abstractmethod
    def get_type(self) -> Type:
        """Return the type of the S-expression."""
        pass

    @abstractmethod
    def substitute(self, mapping: Mapping[Var, SExpr]) -> SExpr:
        """The term with every variable in `mapping` replaced, simultaneously. Unchanged subterms are shared."""


@intern
@dataclass(slots=True, frozen=True, eq=False)
class Constant(SExpr):
    # True == 1 in Python: the key of the pool includes the type of the value, so Bool and Int never collide
    value: Union[int, bool]

    if TYPE_CHECKING:

        @staticmethod
        def make(*, value: int | bool) -> Constant: ...

    @override
    def get_type(self) -> Type:
        return Type.Bool if isinstance(self.value, bool) else Type.Int

    @override
    def to_smt(self) -> str:
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        return str(self.value) if self.value >= 0 else f"(- {-self.value})"

    @override
    def free_variables(self) -> Iterator[Var]:
        return iter(())

    @override
    def substitute(self, mapping: Mapping[Var, SExpr]) -> SExpr:
        return self


@intern
@dataclass(slots=True, frozen=True, eq=False)
class Var(SExpr):
    name: str
    type: Type

    if TYPE_CHECKING:

        @staticmethod
        def make(*, name: str, type: Type) -> Var: ...

    @override
    def get_type(self) -> Type:
        return self.type

    @override
    def to_smt(self) -> str:
        return self.name

    @override
    def free_variables(self) -> Iterator[Var]:
        yield self

    @override
    def substitute(self, mapping: Mapping[Var, SExpr]) -> SExpr:
        return mapping.get(self, self)

    def declaration(self) -> str:
        """Return the SMT-LIB declaration of the variable."""
        return f"({self.name} {self.type.value})"


@intern
@dataclass(slots=True, frozen=True, eq=False)
class OpExpr(SExpr):
    op: Operator
    args: tuple[SExpr, ...]

    if TYPE_CHECKING:

        @staticmethod
        def make(*, op: Operator, args: Iterable[SExpr | int | bool]) -> OpExpr: ...

    @staticmethod
    def __intern_args__(op: Operator, args: Iterable[SExpr | int | bool]) -> dict[str, Any]:
        return {"op": op, "args": tuple(as_term(arg) for arg in args)}

    @override
    def get_type(self) -> Type:
        if self.op in ARITHMETIC_OPS:
            return Type.Int
        if self.op is Operator.ITE:
            return self.args[1].get_type()
        return Type.Bool

    @override
    def to_smt(self) -> str:
        args_str = " ".join(arg.to_smt() for arg in self.args)
        return f"({self.op.value} {args_str})"

    @override
    def free_variables(self) -> Iterator[Var]:
        for arg in self.args:
            yield from arg.free_variables()

    @override
    def substitute(self, mapping: Mapping[Var, SExpr]) -> SExpr:
        if not mapping:
            return self
        args = tuple(arg.substitute(mapping) for arg in self.args)
        return self if all(a is b for a, b in zip(self.args, args)) else OpExpr.make(op=self.op, args=args)


TRUE = Constant.make(value=True)
FALSE = Constant.make(value=False)


def as_term(arg: SExpr | int | bool) -> SExpr:
    """`arg` as a term, a Python int or bool becomes a constant."""
    return arg if isinstance(arg, SExpr) else Constant.make(value=arg)


def Max(first: SExpr | int, *rest: SExpr | int) -> SExpr:  # noqa: N802
    """The largest of the arguments, as a chain of ite."""
    result = as_term(first)
    for arg in rest:
        other = as_term(arg)
        result = OpExpr.make(op=Operator.ITE, args=(OpExpr.make(op=Operator.GE, args=(result, other)), result, other))
    return result
