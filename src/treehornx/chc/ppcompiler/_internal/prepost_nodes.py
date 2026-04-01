from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AstNode:
    text: str
    line: int
    column: int


@dataclass(frozen=True)
class BinaryOperator(AstNode):
    left: AstNode
    right: AstNode


@dataclass(frozen=True)
class UnaryOperator(AstNode):
    operand: AstNode


# ── Atoms ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Var(AstNode):
    name: str


@dataclass(frozen=True)
class Field(AstNode):
    name: str  # identifier after '#'


@dataclass(frozen=True)
class ParentState(AstNode):
    state: str  # identifier after '#:'


@dataclass(frozen=True)
class FieldState(AstNode):
    field: str
    state: str


@dataclass(frozen=True)
class NodeState(AstNode):
    node: str
    state: str


@dataclass(frozen=True)
class Parent(AstNode):
    pass


@dataclass(frozen=True)
class EnumIVariant(AstNode):
    type_name: str
    variant: str


# ── Arithmetic PrePostNodeessions ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Nat(AstNode):
    value: int


@dataclass(frozen=True)
class Neg(UnaryOperator):
    pass


@dataclass(frozen=True)
class Add(BinaryOperator):
    pass


@dataclass(frozen=True)
class Sub(BinaryOperator):
    pass


@dataclass(frozen=True)
class Mul(BinaryOperator):
    pass


@dataclass(frozen=True)
class Div(BinaryOperator):
    pass


type CmpOp = Literal["=", ">", ">=", "<", "<="]


# ── Boolean PrePostNodeessions ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class T(AstNode):
    pass


@dataclass(frozen=True)
class F(AstNode):
    pass


@dataclass(frozen=True)
class Not(UnaryOperator):
    pass


@dataclass(frozen=True)
class And(BinaryOperator):
    pass


@dataclass(frozen=True)
class Or(BinaryOperator):
    pass


@dataclass(frozen=True)
class IfThenElse(AstNode):
    condition: AstNode
    then_: AstNode
    else_: AstNode


@dataclass(frozen=True)
class IfThen(AstNode):
    condition: AstNode
    then_: AstNode


@dataclass(frozen=True)
class IsNil(UnaryOperator):
    pass


@dataclass(frozen=True)
class IsRoot(UnaryOperator):
    pass


@dataclass(frozen=True)
class IsLeaf(UnaryOperator):
    pass


@dataclass(frozen=True)
class Eq(BinaryOperator):
    pass


@dataclass(frozen=True)
class Gt(BinaryOperator):
    pass


@dataclass(frozen=True)
class Ge(BinaryOperator):
    pass


@dataclass(frozen=True)
class Lt(BinaryOperator):
    pass


@dataclass(frozen=True)
class Le(BinaryOperator):
    pass


@dataclass(frozen=True)
class Iff(BinaryOperator):
    pass


@dataclass(frozen=True)
class Application(AstNode):
    name: Id
    args: tuple[AstNode, ...]


@dataclass(frozen=True)
class Id(AstNode):
    pass


@dataclass(frozen=True)
class MacroDecl(AstNode):
    macro_id: Id
    params: tuple[Id, ...]
    body: AstNode


@dataclass(frozen=True)
class VarDecl(AstNode):
    var_id: Id


@dataclass(frozen=True)
class EnumDecl(AstNode):
    enum_id: Id


@dataclass(frozen=True)
class FormulaDecl(AstNode):
    formula: AstNode


type Stmt = MacroDecl | VarDecl | EnumDecl | FormulaDecl
