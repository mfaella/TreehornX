"""Intermediate representation for tree-manipulating programs.

The IR mirrors the language of Faella & Parlato, "Verifying Tree-Manipulating
Programs via CHCs" (Sec. 2):

* every heap statement touches at most one pointer dereference and never
  mixes a dereference with a data expression;
* the only branching statement is ``IfGoto``; loops are lowered to
  ``IfGoto`` + ``Goto``;
* the program ends with ``Exit``.

Identifiers
-----------
Pointer variables, data variables, pointer fields and data fields live in
four separate namespaces, each numbered 0, 1, 2, ... in declaration order.
The root (the function parameter) is always pointer variable 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator, List, Optional, Tuple, Union


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------

class DataType(Enum):
    INT = "int"
    BOOL = "bool"

    def __str__(self) -> str:
        return self.value


# --------------------------------------------------------------------------
# Data expressions (over data variables and constants only)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Const:
    value: Union[int, bool]
    type: DataType


@dataclass(frozen=True)
class Var:
    """Reference to a data variable by id."""
    id: int


@dataclass(frozen=True)
class UnOp:
    op: str            # '-', '!'
    operand: "DataExpr"


@dataclass(frozen=True)
class BinOp:
    op: str            # + - * / %  < <= > >= == !=  && ||
    left: "DataExpr"
    right: "DataExpr"


DataExpr = Union[Const, Var, UnOp, BinOp]
Atom = Union[Const, Var]


# --------------------------------------------------------------------------
# Conditions usable by IfGoto
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PtrEq:
    """``left == right`` (or ``!=`` when negated) between pointer variables."""
    left: int
    right: int
    negated: bool = False


@dataclass(frozen=True)
class IsNil:
    """``ptr == NULL`` (or ``!= NULL`` when negated)."""
    ptr: int
    negated: bool = False


@dataclass(frozen=True)
class DataCond:
    """A Boolean data expression."""
    expr: DataExpr


HeapCond = Union[PtrEq, IsNil]
Cond = Union[PtrEq, IsNil, DataCond]


def negate(c: Cond) -> Cond:
    if isinstance(c, PtrEq):
        return PtrEq(c.left, c.right, not c.negated)
    if isinstance(c, IsNil):
        return IsNil(c.ptr, not c.negated)
    e = c.expr
    if isinstance(e, UnOp) and e.op == "!":
        return DataCond(e.operand)
    if isinstance(e, Const):
        return DataCond(Const(not e.value, DataType.BOOL))
    if isinstance(e, BinOp) and e.op in _FLIP:
        return DataCond(BinOp(_FLIP[e.op], e.left, e.right))
    return DataCond(UnOp("!", e))


_FLIP = {"==": "!=", "!=": "==", "<": ">=", ">=": "<", ">": "<=", "<=": ">"}


# --------------------------------------------------------------------------
# Statements
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AssignData:
    """d := expr"""
    target: int
    expr: DataExpr


@dataclass(frozen=True)
class AssignCond:
    """dbool := heap_cond   (p == q, p != q, p == NULL, p != NULL)"""
    target: int
    cond: HeapCond


@dataclass(frozen=True)
class AssignNil:
    """p := nil"""
    target: int


@dataclass(frozen=True)
class AssignPtr:
    """p := q"""
    target: int
    source: int


@dataclass(frozen=True)
class LoadPtrField:
    """p := q->pfield"""
    target: int
    source: int
    field: int


@dataclass(frozen=True)
class StoreNilField:
    """p->pfield := nil"""
    ptr: int
    field: int


@dataclass(frozen=True)
class StorePtrField:
    """p->pfield := q"""
    ptr: int
    field: int
    source: int


@dataclass(frozen=True)
class LoadDataField:
    """d := p->dfield"""
    target: int
    ptr: int
    field: int


@dataclass(frozen=True)
class StoreDataField:
    """p->dfield := atom   (a data variable or a constant)"""
    ptr: int
    field: int
    value: Atom


@dataclass(frozen=True)
class New:
    """new p   (from ``p = malloc(sizeof(struct NODE))``)"""
    target: int


@dataclass(frozen=True)
class Free:
    """free p"""
    ptr: int


@dataclass(frozen=True)
class IfGoto:
    """if cond then goto target else fall through to pc+1"""
    cond: Cond
    target: int


@dataclass(frozen=True)
class Goto:
    target: int


@dataclass(frozen=True)
class Exit:
    pass


Stmt = Union[AssignData, AssignCond, AssignNil, AssignPtr, LoadPtrField,
             StoreNilField, StorePtrField, LoadDataField, StoreDataField,
             New, Free, IfGoto, Goto, Exit]

HEAP_STMTS = (AssignNil, AssignPtr, LoadPtrField, StoreNilField,
              StorePtrField, LoadDataField, StoreDataField, New, Free)


# --------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DataField:
    id: int
    name: str
    type: DataType


@dataclass(frozen=True)
class PointerField:
    id: int
    name: str


@dataclass(frozen=True)
class DataVariable:
    id: int
    name: str
    type: DataType


@dataclass(frozen=True)
class PointerVariable:
    id: int
    name: str


@dataclass(frozen=True)
class NodeStruct:
    name: str
    data_fields: Tuple[DataField, ...]
    pointer_fields: Tuple[PointerField, ...]

    @property
    def k(self) -> int:
        """Number of pointer fields (the arity of the tree)."""
        return len(self.pointer_fields)

    def data_field_type(self, fid: int) -> DataType:
        return self.data_fields[fid].type

    def data_field_id(self, name: str) -> int:
        for f in self.data_fields:
            if f.name == name:
                return f.id
        raise KeyError(name)

    def pointer_field_id(self, name: str) -> int:
        for f in self.pointer_fields:
            if f.name == name:
                return f.id
        raise KeyError(name)


# --------------------------------------------------------------------------
# Function
# --------------------------------------------------------------------------

NextPc = Union[None, int, Tuple[int, int]]


@dataclass(frozen=True)
class Function:
    name: str
    node: NodeStruct
    pointer_vars: Tuple[PointerVariable, ...]   # pointer_vars[0] is the root
    data_vars: Tuple[DataVariable, ...]
    statements: Tuple[Stmt, ...]

    ROOT: int = 0

    # ---- queries ---------------------------------------------------------
    def __len__(self) -> int:
        return len(self.statements)

    def __iter__(self) -> Iterator[Tuple[int, Stmt]]:
        return iter(enumerate(self.statements))

    def statement(self, pc: int) -> Stmt:
        if not 0 <= pc < len(self.statements):
            raise IndexError(f"pc {pc} out of range [0, {len(self.statements)})")
        return self.statements[pc]

    def __getitem__(self, pc: int) -> Stmt:
        """Tuple-style indexing (negative indices allowed)."""
        return self.statements[pc]

    @property
    def root(self) -> PointerVariable:
        return self.pointer_vars[self.ROOT]

    def data_field_type(self, fid: int) -> DataType:
        return self.node.data_field_type(fid)

    def data_field_types(self) -> List[DataType]:
        return [f.type for f in self.node.data_fields]

    def data_var_type(self, vid: int) -> DataType:
        return self.data_vars[vid].type

    def data_var_types(self) -> List[DataType]:
        return [v.type for v in self.data_vars]

    def next_pc(self, pc: int) -> NextPc:
        """Successor(s) of ``pc``.

        * ``Exit``   -> ``None``
        * ``Goto``   -> the target pc
        * ``IfGoto`` -> ``(pc_if_true, pc_if_false)`` i.e. ``(target, pc + 1)``
        * otherwise  -> ``pc + 1``
        """
        s = self.statement(pc)
        if isinstance(s, Exit):
            return None
        if isinstance(s, Goto):
            return s.target
        if isinstance(s, IfGoto):
            return (s.target, pc + 1)
        return pc + 1

    def successors(self, pc: int) -> Tuple[int, ...]:
        n = self.next_pc(pc)
        if n is None:
            return ()
        return n if isinstance(n, tuple) else (n,)

    # ---- name lookup -----------------------------------------------------
    def pointer_var_id(self, name: str) -> int:
        for v in self.pointer_vars:
            if v.name == name:
                return v.id
        raise KeyError(name)

    def data_var_id(self, name: str) -> int:
        for v in self.data_vars:
            if v.name == name:
                return v.id
        raise KeyError(name)

    # ---- pretty printing -------------------------------------------------
    def fmt_expr(self, e: DataExpr) -> str:
        if isinstance(e, Const):
            if e.type is DataType.BOOL:
                return "true" if e.value else "false"
            return str(e.value)
        if isinstance(e, Var):
            return self.data_vars[e.id].name
        if isinstance(e, UnOp):
            return f"{e.op}{self._paren(e.operand)}"
        return f"{self._paren(e.left)} {e.op} {self._paren(e.right)}"

    def _paren(self, e: DataExpr) -> str:
        s = self.fmt_expr(e)
        return f"({s})" if isinstance(e, (BinOp, UnOp)) else s

    def fmt_cond(self, c: Cond) -> str:
        p = lambda i: self.pointer_vars[i].name  # noqa: E731
        if isinstance(c, PtrEq):
            return f"{p(c.left)} {'!=' if c.negated else '=='} {p(c.right)}"
        if isinstance(c, IsNil):
            return f"{p(c.ptr)} {'!=' if c.negated else '=='} nil"
        return self.fmt_expr(c.expr)

    def fmt_stmt(self, s: Stmt) -> str:
        p = lambda i: self.pointer_vars[i].name  # noqa: E731
        d = lambda i: self.data_vars[i].name     # noqa: E731
        pf = lambda i: self.node.pointer_fields[i].name  # noqa: E731
        df = lambda i: self.node.data_fields[i].name     # noqa: E731
        if isinstance(s, AssignData):
            return f"{d(s.target)} := {self.fmt_expr(s.expr)}"
        if isinstance(s, AssignCond):
            return f"{d(s.target)} := ({self.fmt_cond(s.cond)})"
        if isinstance(s, AssignNil):
            return f"{p(s.target)} := nil"
        if isinstance(s, AssignPtr):
            return f"{p(s.target)} := {p(s.source)}"
        if isinstance(s, LoadPtrField):
            return f"{p(s.target)} := {p(s.source)}->{pf(s.field)}"
        if isinstance(s, StoreNilField):
            return f"{p(s.ptr)}->{pf(s.field)} := nil"
        if isinstance(s, StorePtrField):
            return f"{p(s.ptr)}->{pf(s.field)} := {p(s.source)}"
        if isinstance(s, LoadDataField):
            return f"{d(s.target)} := {p(s.ptr)}->{df(s.field)}"
        if isinstance(s, StoreDataField):
            return f"{p(s.ptr)}->{df(s.field)} := {self.fmt_expr(s.value)}"
        if isinstance(s, New):
            return f"new {p(s.target)}"
        if isinstance(s, Free):
            return f"free {p(s.ptr)}"
        if isinstance(s, IfGoto):
            return f"if {self.fmt_cond(s.cond)} goto {s.target}"
        if isinstance(s, Goto):
            return f"goto {s.target}"
        if isinstance(s, Exit):
            return "exit"
        raise TypeError(s)

    def __str__(self) -> str:
        lines = [f"struct {self.node.name} {{"]
        for f in self.node.data_fields:
            lines.append(f"  data    #{f.id} {f.type} {f.name}")
        for f in self.node.pointer_fields:
            lines.append(f"  pointer #{f.id} {f.name}")
        lines.append("}")
        lines.append(f"function {self.name}")
        for v in self.pointer_vars:
            tag = "  (root)" if v.id == self.ROOT else ""
            lines.append(f"  pointer var #{v.id} {v.name}{tag}")
        for v in self.data_vars:
            lines.append(f"  data var    #{v.id} {v.type} {v.name}")
        width = len(str(len(self.statements) - 1))
        for pc, s in self:
            lines.append(f"  {pc:>{width}}: {self.fmt_stmt(s)}")
        return "\n".join(lines)
