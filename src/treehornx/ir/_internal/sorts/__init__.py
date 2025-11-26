"""Sort system for Knit's intermediate representation.

This module defines the type system (sorts) used in the IR. A sort is a type
classification that values can have. The module provides native sorts (INT, REAL,
POINTER, BOOL, UNIT) and enumerated sorts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, override


@dataclass(frozen=True)
class Sort:
    """Base class for all sorts in the IR.

    A sort represents a type classification in knit-ir's type system.

    Attributes:
        name: The name of the sort.
    """

    name: str

    _pool: ClassVar[dict[Sort, Sort]] = {}

    def __new__(cls, *args: Any, **kwargs: dict[str, Any]) -> Sort:
        """Create or retrieve an interned Enum instance.

        Args:
            name: The name of the enumeration.
            values: Tuple of allowed values.

        Returns:
            An Enum instance, reusing existing instances with the same
            name and values.
        """
        instance = object.__new__(cls)
        cls.__init__(instance, *args, **kwargs)
        if instance not in cls._pool:
            cls._pool[instance] = instance
        return cls._pool[instance]

    @override
    def __str__(self) -> str:
        """Return the sort's name as its string representation."""
        return self.name

    def is_int(self) -> bool:
        """Check if this sort is INT.

        Returns:
            True if this sort is INT.
        """
        return False

    def is_real(self) -> bool:
        """Check if this sort is REAL.

        Returns:
            True if this sort is REAL.
        """
        return False

    def is_unit(self) -> bool:
        """Check if this sort is UNIT.

        Returns:
            True if this sort is UNIT.
        """
        return False

    def is_enum(self) -> bool:
        """Check if this sort is an Enum type.

        Returns:
            True if this sort is an Enum type.
        """
        return False

    def is_struct(self) -> bool:
        """Check if this sort is a Struct type.

        Returns:
            True if this sort is a Struct type.
        """
        return False

    def is_ptr(self) -> bool:
        """Check if this sort is POINTER.

        Returns:
            True if this sort is POINTER.
        """
        return False


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


@dataclass(frozen=True)
class Enum(Sort):
    """A sort representing an enumerated type with a fixed set of values.

    Uses object interning to ensure that enums with the same name and values
    are the same object instance, allowing for efficient identity checks.

    Attributes:
        name: The name of the enumeration.
        values: Tuple of allowed string values for this enum.

    Example:
        >>> color = Enum("Color", ("RED", "GREEN", "BLUE"))
        >>> color.contains("RED")
        True
        >>> str(color)
        'Color[RED, GREEN, BLUE]'
    """

    values: tuple[str, ...]

    def contains(self, value: str) -> bool:
        """Check if a value is valid for this enum.

        Args:
            value: The value to check.

        Returns:
            True if the value is in this enum's allowed values.
        """
        return value in self.values

    @override
    def __str__(self) -> str:
        """Return formatted string representation of the enum."""
        return f"{self.name}[{', '.join(self.values)}]"

    @override
    def is_enum(self) -> bool:
        return True


@dataclass(frozen=True, init=False, repr=False)
class Pointer(Sort):
    """A sort representing a pointer type pointing to another sort.

    Attributes:
        pointee: The sort that this pointer points to.
    """

    sort: Sort = field(hash=False, compare=False)
    _sort_id: int = field(init=False, repr=False, compare=False)

    def __init__(self, sort: Sort):
        super().__init__(name=f"pointer[{sort}]")
        object.__setattr__(self, "sort", sort)
        object.__setattr__(self, "_sort_id", id(sort))

    @override
    def is_ptr(self) -> bool:
        return True

    @override
    def __repr__(self) -> str:
        return f"{self.sort}"


INT = Int()
"""Native sort representing integer numeric types."""

REAL = Real()
"""Native sort representing real/floating-point numeric types."""

BOOL = Enum("bool", ("TRUE", "FALSE"))
"""Native sort representing boolean types with values TRUE and FALSE."""

UNIT = Unit()
"""Native sort representing the unit type (similar to void)."""
