"""Minimal SMT-LIB2 terms for CHC systems over integers and booleans.

Terms are immutable and hash-consed: a constructor returns the cached instance of a term already alive, so equality
and hashing are by identity. Free variables of a
clause are universally quantified when the clause is printed, predicates are declared by the system using them.
"""

from __future__ import annotations

import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import IO, Callable, Iterable, Iterator, Literal, Optional, TypeVar, Union, cast
from weakref import WeakValueDictionary

from typing_extensions import override


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


@dataclass(slots=True, frozen=True, eq=False, init=False)
class Constant(SExpr):
    value: Union[int, bool]

    def __new__(cls, value: int | bool) -> Constant:
        # True == 1 in Python: Bool and Int constants live in separate caches, so that they never collide
        if isinstance(value, bool):
            return _cached(_bools, value, cls, value=value)
        return _cached(_ints, value, cls, value=value)

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


@dataclass(slots=True, frozen=True, eq=False, init=False)
class Var(SExpr):
    name: str
    type: Type

    def __new__(cls, name: str, type: Type) -> Var:
        return _cached(_vars[type], name, cls, name=name, type=type)

    @override
    def get_type(self) -> Type:
        return self.type

    @override
    def to_smt(self) -> str:
        return self.name

    @override
    def free_variables(self) -> Iterator[Var]:
        yield self

    def declaration(self) -> str:
        """Return the SMT-LIB declaration of the variable."""
        return f"({self.name} {self.type.value})"


@dataclass(slots=True, frozen=True, eq=False, init=False)
class OpExpr(SExpr):
    op: Operator
    args: tuple[SExpr, ...]

    def __new__(cls, op: Operator, *args: SExpr | int | bool) -> OpExpr:
        terms = tuple(_term(arg) for arg in args)
        return _cached(_op_exprs, (op, terms), cls, op=op, args=terms)

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


@dataclass(slots=True, frozen=True, eq=False, init=False, weakref_slot=True)
class Predicate:
    name: str
    types: tuple[Type, ...]

    def __new__(cls, name: str, types: Iterable[Type]) -> Predicate:
        signature = tuple(types)
        return _cached(_predicates, (name, signature), cls, name=name, types=signature)

    def smt_declaration(self) -> str:
        """Return the SMT-LIB declaration of the predicate."""
        types_str = " ".join(t.value for t in self.types)
        return f"(declare-fun {self.name} ({types_str}) Bool)"


@dataclass(slots=True, frozen=True, eq=False, init=False)
class Application(SMTNode):
    predicate: Predicate
    args: tuple[SExpr, ...]

    def __new__(cls, predicate: Predicate, *args: SExpr | int | bool) -> Application:
        assert len(args) == len(predicate.types), f"{predicate.name} takes {len(predicate.types)} arguments"
        terms = tuple(_term(arg) for arg in args)
        return _cached(_applications, (predicate, terms), cls, predicate=predicate, args=terms)

    @override
    def to_smt(self) -> str:
        if not self.args:
            return self.predicate.name
        args_str = " ".join(arg.to_smt() for arg in self.args)
        return f"({self.predicate.name} {args_str})"

    @override
    def free_variables(self) -> Iterator[Var]:
        for arg in self.args:
            yield from arg.free_variables()


@dataclass(slots=True, frozen=True, eq=False, init=False)
class Clause(SMTNode):
    """body → head, `head` is False for a query."""

    head: Application | Literal[False]
    body: tuple[SExpr | Application, ...]

    def __new__(cls, head: Application | Literal[False], *body: SExpr | Application) -> Clause:
        assert not (head is False and not any(isinstance(conj, Application) for conj in body))
        return _cached(_clauses, (head, body), cls, head=head, body=body)

    @override
    def free_variables(self) -> Iterator[Var]:
        if isinstance(self.head, Application):
            yield from self.head.free_variables()
        for b in self.body:
            yield from b.free_variables()

    def applications(self) -> Iterator[Application]:
        if isinstance(self.head, Application):
            yield self.head
        for b in self.body:
            if isinstance(b, Application):
                yield b

    @override
    def to_smt(self) -> str:
        head_str = self.head.to_smt() if isinstance(self.head, Application) else "false"
        match self.body:
            case ():
                implication = head_str
            case (single,):
                implication = f"(=> {single.to_smt()} {head_str})"
            case _:
                body_str = " ".join(b.to_smt() for b in self.body)
                implication = f"(=> (and {body_str}) {head_str})"
        variables = sorted(set(self.free_variables()), key=lambda v: v.name)
        if not variables:
            return f"(assert {implication})"
        var_decls = " ".join(v.declaration() for v in variables)
        return f"(assert (forall ({var_decls}) {implication}))"


Transform = Callable[[Clause], Optional[Clause]]
"""A rewriting applied to every clause when it is printed; None drops the clause."""


def transformed(clauses: Iterable[Clause], transform: Transform | None) -> Iterator[Clause]:
    """`clauses` rewritten one at a time by `transform`, the dropped ones left out."""
    if transform is None:
        yield from clauses
        return
    for clause in clauses:
        if (result := transform(clause)) is not None:
            yield result


def write_horn(clauses: Iterable[Clause], out: IO[str], transform: Transform | None = None) -> None:
    """Writes the HORN script of `clauses`, declaring the predicates they use.

    The clauses are consumed once: each one is rewritten by `transform` and spooled to a temporary file while the
    used predicates are collected, then copied after the declarations, so a lazily generated system is never held
    in memory, before or after the rewriting."""
    used: dict[str, Predicate] = {}
    with tempfile.TemporaryFile("w+") as spool:
        for clause in transformed(clauses, transform):
            for app in clause.applications():
                used.setdefault(app.predicate.name, app.predicate)
            spool.write(clause.to_smt())
            spool.write("\n")

        out.write("(set-logic HORN)\n")
        for name in sorted(used):
            out.write(used[name].smt_declaration())
            out.write("\n")
        out.write("\n")
        spool.seek(0)
        shutil.copyfileobj(spool, out)
        out.write("(check-sat)\n")


@dataclass
class CHCSystem:
    predicates: list[Predicate] = field(default_factory=list[Predicate])
    clauses: list[Clause] = field(default_factory=list[Clause])
    """The clauses as built, `transform` is applied only when they are printed."""
    transform: Transform | None = None

    def printed_clauses(self) -> Iterator[Clause]:
        """The clauses as they are printed, rewritten lazily by `transform`."""
        return transformed(self.clauses, self.transform)

    def write(self, out: IO[str]) -> None:
        write_horn(self.clauses, out, self.transform)

    def to_smt(self) -> str:
        """The SMT-LIB script of the system, only the predicates used by some printed clause are declared."""
        clauses = list(self.printed_clauses())
        lines = ["(set-logic HORN)"]
        used = {app.predicate.name: app.predicate for clause in clauses for app in clause.applications()}
        lines += [used[name].smt_declaration() for name in sorted(used)]
        lines.append("")
        lines += [clause.to_smt() for clause in clauses]
        lines.append("(check-sat)")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# hash-consing
# ---------------------------------------------------------------------------
# One cache per class, so that the class is not part of the key. Every cache maps a key built from the arguments of
# a node (themselves canonical) to the canonical instance alive.

K = TypeVar("K")
N = TypeVar("N", bound=Union[SMTNode, Predicate])

_ints: WeakValueDictionary[int, Constant] = WeakValueDictionary()
_bools: WeakValueDictionary[bool, Constant] = WeakValueDictionary()
_vars: dict[Type, WeakValueDictionary[str, Var]] = {t: WeakValueDictionary() for t in Type}
_op_exprs: WeakValueDictionary[tuple[Operator, tuple[SExpr, ...]], OpExpr] = WeakValueDictionary()
_predicates: WeakValueDictionary[tuple[str, tuple[Type, ...]], Predicate] = WeakValueDictionary()
_applications: WeakValueDictionary[tuple[Predicate, tuple[SExpr, ...]], Application] = WeakValueDictionary()
_clauses: WeakValueDictionary[tuple[Application | Literal[False], tuple[SExpr | Application, ...]], Clause] = (
    WeakValueDictionary()
)


def _cached(cache: WeakValueDictionary[K, N], key: K, cls: type[N], **fields: object) -> N:
    """The node of `key` in `cache`, or a new `cls` with `fields`, cached."""
    node = cache.get(key)
    if node is None:
        node = object.__new__(cls)
        for name, value in fields.items():
            object.__setattr__(node, name, value)
        cache[key] = node
    return node


TRUE = Constant(True)
FALSE = Constant(False)


def reset_env() -> None:
    """Empties the caches: nodes built before the call are no longer equal to the ones built after it."""
    for cache in (_ints, _bools, *_vars.values(), _op_exprs, _predicates, _applications, _clauses):
        cache.clear()
    for node in (TRUE, FALSE):
        _bools[cast(bool, node.value)] = node


def _term(arg: SExpr | int | bool) -> SExpr:
    return arg if isinstance(arg, SExpr) else Constant(arg)


def Max(first: SExpr | int, *rest: SExpr | int) -> SExpr:  # noqa: N802
    """The largest of the arguments, as a chain of ite."""
    result = _term(first)
    for arg in rest:
        other = _term(arg)
        result = OpExpr(Operator.ITE, OpExpr(Operator.GE, result, other), result, other)
    return result
