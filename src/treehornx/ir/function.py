from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

from .enviroment import Enviroment
from .expressions import Expr, Field, Operator, Var, sort_of
from .instructions import (
    FieldAssignExpr,
    FieldAssignNil,
    FieldAssignPtr,
    Free,
    Goto,
    IfGoto,
    Instruction,
    InstructionInfo,
    New,
    PtrAssignField,
    PtrAssignNil,
    PtrAssignPtr,
    Return,
    VarAssignExpr,
)
from .sorts import UNIT, Pointer, Sort


@dataclass(frozen=True, slots=True)
class Function:
    """A compiled-like representation of a function in the IR.

    Attributes:
        name: The function name.
        env: The `Enviroment` describing parameters, locals and fields.
        return_type: The function return `Sort`.
        instructions: A sequence of `Instruction` objects forming the function body.
    """

    name: str
    env: Enviroment
    return_type: Sort
    instructions: Sequence[Instruction]

    _info: dict[int, InstructionInfo] = field(init=False, default_factory=lambda: {})

    def _build_labels(self) -> dict[str, int]:
        labels: dict[str, int] = dict()
        for idx, instr in enumerate(self.instructions):
            if instr.label is not None:
                if instr.label in labels:
                    raise ValueError(f"Duplicate label: {instr.label}")
                labels[instr.label] = idx
        return labels

    def _build_info(self, labels: dict[str, int]) -> dict[int, InstructionInfo]:
        info: dict[int, InstructionInfo] = dict()
        for idx, instr in enumerate(self.instructions):
            if isinstance(instr, IfGoto):
                next_pc_true = labels[instr.target]
                next_pc_false = idx + 1
                info[id(instr)] = InstructionInfo(idx, (next_pc_true, next_pc_false))
            elif isinstance(instr, Goto):
                next_pc = labels[instr.target]
                info[id(instr)] = InstructionInfo(idx, next_pc)
            else:
                info[id(instr)] = InstructionInfo(idx, idx + 1)
        return info

    # ruff: noqa: PLR0912
    def _validate_instruction(self, instr: Instruction) -> None:
        match instr:
            case IfGoto(condition, _):
                self._validate_expression(condition)
            case PtrAssignNil(ptr):
                self._validate_expression(ptr)
            case PtrAssignPtr(src, dst):
                self._validate_expression(src)
                self._validate_expression(dst)
            case PtrAssignField(ptr, field):
                self._validate_expression(ptr)
                self._validate_expression(field)
            case FieldAssignNil(ptr):
                self._validate_expression(ptr)
            case FieldAssignPtr(src, dst):
                self._validate_expression(src)
                self._validate_expression(dst)
            case VarAssignExpr(var, expr):
                self._validate_expression(var)
                self._validate_expression(expr)
            case FieldAssignExpr(field, expr):
                self._validate_expression(field)
                self._validate_expression(expr)
            case Return(value) if value is not None:
                self._validate_expression(value)
            case Free(pointer) | New(pointer):
                if pointer.sort.sort is not self.env.node_sort:  # type: ignore
                    raise ValueError(f"pointer.sort.sort is not self.env.node_sort")
            case Return(expr) if expr is not None:
                self._validate_expression(expr)
            case _:
                pass

    def _validate_expression(self, op: Expr) -> None:
        match op:
            case Var(_, _):
                if op not in self.env.vars:
                    raise ValueError(f"Variable {op} not in environment")
                sort_op = sort_of(op)
                if not sort_op.is_ptr():
                    return
                sort_op = cast(Pointer, sort_op)
                if sort_op.sort is not self.env.node_sort:
                    raise ValueError(f"Variable {op} has invalid sort")
            case Field(ptr, field):
                self._validate_expression(ptr)
                if field not in self.env.node_sort.fields:
                    raise ValueError(f"Field {field} not in environment")
            case Operator():
                all(self._validate_expression(arg) for arg in op.args())
            case _:
                pass

    def __post_init__(self):
        labels = self._build_labels()
        info = self._build_info(labels)
        object.__setattr__(self, "_info", info)

        for instr in self.instructions:
            self._validate_instruction(instr)

        if not sort_of(self.env.root).is_ptr():
            raise ValueError("sort_of(self.env.root) is not POINTER")

        for instr in self.instructions:
            if isinstance(instr, Return):
                sort = UNIT if instr.value is None else sort_of(instr.value)
                if sort is not self.return_type:
                    raise ValueError(f"sort_of(instr.value) is not self.return_type")

    def info_of(self, instr: Instruction) -> InstructionInfo:
        return self._info[id(instr)]

    def info_at(self, pc: int) -> InstructionInfo:
        instr = self.instructions[pc]
        return self.info_of(instr)
