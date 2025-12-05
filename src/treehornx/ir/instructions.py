from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import override

from .expressions import Expr, Field, Var, sort_of
from .sorts import BOOL


@dataclass(frozen=True, slots=True)
class _Labeled:
    """Base class for instructions that may carry an optional label.

    The ``label`` field, when present, is used as a jump target elsewhere in
    the instruction sequence.

    Attributes:
        label: Optional label string used as a jump target.
    """

    label: str | None = field(kw_only=True, default=None)

    def with_label(self, label: str) -> _Labeled:
        """Return a copy of this instruction with the given label.

        Args:
            label: Label string to attach to the instruction.

        Returns:
            A copy of this instruction with the specified label.
        """
        instr_copy = deepcopy(self)
        object.__setattr__(instr_copy, "label", label)
        return instr_copy


@dataclass(frozen=True, slots=True)
class IfGoto(_Labeled):
    """Conditional jump instruction.

    Args:
        condition: Expression evaluated to choose the branch.
        target: Label name for the 'true' branch.
    """

    condition: Expr
    target: str

    def __post_init__(self):
        if sort_of(self.condition) is not BOOL:
            raise ValueError("Condition of IfElse must be of BOOL sort")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}if {self.condition} goto {self.target}"


@dataclass(frozen=True, slots=True)
class Goto(_Labeled):
    """Unconditional jump to the given label.

    Args:
        target: Label name to jump to.
    """

    target: str

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}goto {self.target}"


@dataclass(frozen=True, slots=True)
class PtrAssignNil(_Labeled):
    """Instruction that sets a pointer variable to nil.

    Args:
        pointer: Pointer-sorted variable to set to nil.
    """

    pointer: Var

    def __post_init__(self):
        if not sort_of(self.pointer).is_ptr():
            raise ValueError("not sort_of(self.pointer).is_ptr()")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}{self.pointer} := nil"


@dataclass(frozen=True, slots=True)
class PtrAssignPtr(_Labeled):
    """Assign the value of one pointer variable to another.

    Both ``dest`` and ``source`` must be pointer-sorted variables.

    Args:
        dest: Destination pointer variable.
        source: Source pointer variable.
    """

    left: Var
    right: Var

    def __post_init__(self):
        if not sort_of(self.left).is_ptr():
            raise ValueError("sort_of(self.left) is not POINTER")
        if not sort_of(self.right).is_ptr():
            raise ValueError("sort_of(self.right) is not POINTER")
        if self.left.sort is not self.right.sort:
            raise ValueError("self.left and self.right must have the same pointer sort")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}{self.left} := {self.right}"


@dataclass(frozen=True, slots=True)
class PtrAssignField(_Labeled):
    """Assign a pointer field value into a pointer variable.

    Args:
        dest: Pointer variable that will receive the value.
        source: ``Field`` expression yielding a pointer value.
    """

    left: Var
    right: Field

    def __post_init__(self):
        if not sort_of(self.left).is_ptr():
            raise ValueError("not sort_of(self.left).is_ptr()")
        if not sort_of(self.right).is_ptr():
            raise ValueError("not sort_of(self.right).is_ptr()")
        if sort_of(self.left) is not sort_of(self.right):
            raise ValueError("sort_of(self.left) is not sort_of(self.right)")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}{self.left} := {self.right}"


@dataclass(frozen=True, slots=True)
class FieldAssignNil(_Labeled):
    """Set a pointer-typed field to nil.

    Args:
        field: Field expression representing the field to set to nil.
    """

    field: Field

    def __post_init__(self):
        if not sort_of(self.field).is_ptr():
            raise ValueError("sort_of(self.field) is not POINTER")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}{self.field} := nil"


@dataclass(frozen=True, slots=True)
class FieldAssignPtr(_Labeled):
    """Assign a pointer variable value into a pointer-typed field.

    Args:
        dest: Field to assign into.
        source: Pointer variable providing the value.
    """

    left: Field
    right: Var

    def __post_init__(self):
        if not sort_of(self.left).is_ptr():
            raise ValueError("sort_of(self.left) is not POINTER")
        if not sort_of(self.right).is_ptr():
            raise ValueError("sort_of(self.right) is not POINTER")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}{self.left} := {self.right}"


@dataclass(frozen=True, slots=True)
class VarAssignExpr(_Labeled):
    """Assign a data expression value into a data variable.

    Args:
        dest: Data variable that will receive the value.
        source: Data expression providing the value.
    """

    left: Var
    right: Expr

    def __post_init__(self):
        if sort_of(self.left).is_ptr():
            raise ValueError("sort_of(self.left).is_ptr()")
        if sort_of(self.left) is not sort_of(self.right):
            raise ValueError("sort_of(self.left) is not sort_of(self.right)")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}{self.left} := {self.right}"


@dataclass(frozen=True, slots=True)
class FieldAssignExpr(_Labeled):
    """Assign a data expression value into a data field.

    Args:
        dest: Field that will receive the value.
        source: Data expression providing the value.
    """

    left: Field
    right: Expr

    def __post_init__(self):
        if sort_of(self.left).is_ptr():
            raise ValueError("sort_of(self.left).is_ptr()")
        if isinstance(self.right, Field):
            raise ValueError("isinstance(self.right, Field)")
        if sort_of(self.left) is not sort_of(self.right):
            raise ValueError("sort_of(self.left) is not sort_of(self.right)")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str} {self.right} := {self.left}"


@dataclass(frozen=True, slots=True)
class New(_Labeled):
    """Allocate a new struct and assign its pointer to a variable.

    Args:
        dest: Pointer variable that will receive the new struct's pointer.
        struct_sort: Sort of the struct to allocate.
    """

    pointer: Var

    def __post_init__(self):
        if not sort_of(self.pointer).is_ptr():
            raise ValueError("sort_of(self.pointer) is not POINTER")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}new {self.pointer}"


@dataclass(frozen=True, slots=True)
class Free(_Labeled):
    """Deallocate the struct pointed to by a pointer variable.

    Args:
        pointer: Pointer variable whose pointee will be deallocated.
    """

    pointer: Var

    def __post_init__(self):
        if not sort_of(self.pointer).is_ptr():
            raise ValueError("not sort_of(self.pointer).is_ptr()")

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str}free {self.pointer}"


@dataclass(frozen=True, slots=True)
class Return(_Labeled):
    """Return instruction.

    Args:
        value: Optional return expression. Use ``None`` for UNIT-returning functions.
    """

    value: Expr | None = None

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        value_str = "" if self.value is None else f" {self.value}"
        return f"{label_str}return{value_str}"


class Skip(_Labeled):
    """No-operation instruction.

    This instruction does nothing and is used as a placeholder.
    """

    @override
    def __str__(self) -> str:
        label_str = "" if self.label is None else f"{self.label}: "
        return f"{label_str} skip"


Instruction = (
    PtrAssignNil
    | PtrAssignPtr
    | PtrAssignField
    | FieldAssignNil
    | FieldAssignPtr
    | IfGoto
    | Goto
    | Return
    | VarAssignExpr
    | FieldAssignExpr
    | New
    | Free
)


@dataclass(frozen=True, slots=True)
class InstructionInfo:
    """Auxiliary information about an instruction's program counter and next PC(s).

    Attributes:
        pc: Instruction index in the function's instruction list.
        next_pc: Either the next instruction index or a tuple for conditional jumps.
    """

    pc: int
    next_pc: int | tuple[int, int]  # next pc or (then_pc, else_pc) for IfElse
