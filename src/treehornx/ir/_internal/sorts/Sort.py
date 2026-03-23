from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, override


@dataclass(frozen=True)
class Sort:
    """Base class for all sorts in the IR.

    A sort represents a type classification in knit-ir's type system.

    Attributes:
        name: The name of the sort.
    """

    name: str

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
