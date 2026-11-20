"""CHC systems over the quantifier-free terms of `treehornx.smt`.

Predicates, applications and clauses are immutable and interned like the terms (`treehornx.intern`): `X.make(...)`
returns the instance of a node already alive, so equality and hashing are by identity. Free variables of a clause are
universally quantified when the clause is printed, predicates are declared by the system using them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Literal

from typing_extensions import override

from treehornx.smt import SExpr, SMTNode, Type, Var, as_term
from treehornx.intern import intern


@intern
@dataclass(slots=True, frozen=True, eq=False, weakref_slot=True)
class Predicate:
    name: str
    types: tuple[Type, ...]

    if TYPE_CHECKING:

        @staticmethod
        def make(*, name: str, types: Iterable[Type]) -> Predicate: ...

    @staticmethod
    def __intern_args__(name: str, types: Iterable[Type]) -> dict[str, Any]:
        return {"name": name, "types": tuple(types)}

    def smt_declaration(self) -> str:
        """Return the SMT-LIB declaration of the predicate."""
        types_str = " ".join(t.value for t in self.types)
        return f"(declare-fun {self.name} ({types_str}) Bool)"


@intern
@dataclass(slots=True, frozen=True, eq=False)
class Application(SMTNode):
    predicate: Predicate
    args: tuple[SExpr, ...]

    if TYPE_CHECKING:

        @staticmethod
        def make(*, predicate: Predicate, args: Iterable[SExpr | int | bool]) -> Application: ...

    @staticmethod
    def __intern_args__(predicate: Predicate, args: Iterable[SExpr | int | bool]) -> dict[str, Any]:
        terms = tuple(as_term(arg) for arg in args)
        assert len(terms) == len(predicate.types), f"{predicate.name} takes {len(predicate.types)} arguments"
        return {"predicate": predicate, "args": terms}

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


@intern
@dataclass(slots=True, frozen=True, eq=False)
class Clause(SMTNode):
    """body → head, `head` is False for a query."""

    head: Application | Literal[False]
    body: tuple[SExpr | Application, ...]

    if TYPE_CHECKING:

        @staticmethod
        def make(*, head: Application | Literal[False], body: Iterable[SExpr | Application]) -> Clause: ...

    @staticmethod
    def __intern_args__(head: Application | Literal[False], body: Iterable[SExpr | Application]) -> dict[str, Any]:
        conjuncts = tuple(body)
        assert not (head is False and not any(isinstance(conj, Application) for conj in conjuncts))
        return {"head": head, "body": conjuncts}

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
