"""Sort system for Knit's intermediate representation.

This module defines the type system (sorts) used in the IR. A sort is a type
classification that values can have. The module provides native sorts (INT, REAL,
POINTER, BOOL, UNIT) and enumerated sorts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, override

from .Sort import Sort


@dataclass(frozen=True, init=False)
class Int(Sort):
    """Internal class representing built-in native sorts."""

    def __init__(self):
        super().__init__(name="int")

    @override
    def is_int(self) -> bool:
        return True


@dataclass(frozen=True, init=False)
class Real(Sort):
    """Internal class representing built-in native sorts."""

    def __init__(self):
        super().__init__(name="real")

    @override
    def is_real(self) -> bool:
        return True


@dataclass(frozen=True, init=False)
class Unit(Sort):
    """Internal class representing built-in native sorts."""

    def __init__(self):
        super().__init__(name="unit")

    @override
    def is_unit(self) -> bool:
        return True


@dataclass(frozen=True, init=False, repr=False)
class Pointer(Sort):
    """A sort representing a pointer type pointing to another sort.

    Attributes:
        pointee: The sort that this pointer points to.
    """

    pointee: Sort = field(hash=False, compare=False)
    _pointee_id: int = field(init=False, repr=False)

    def __init__(self, pointee: Sort):
        super().__init__(name=f"pointer[{pointee}]")
        object.__setattr__(self, "pointee", pointee)
        object.__setattr__(self, "_pointee_id", id(pointee))

    @override
    def is_ptr(self) -> bool:
        return True

    @override
    def __repr__(self) -> str:
        return f"{self.pointee}"


INT = Int()
"""Native sort representing integer numeric types."""

REAL = Real()
"""Native sort representing real/floating-point numeric types."""

UNIT = Unit()
"""Native sort representing the unit type (similar to void)."""
