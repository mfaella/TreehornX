from dataclasses import dataclass
from typing import override

from frozendict import frozendict

from .Sort import Sort


@dataclass(frozen=True, init=False)
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

    flags: frozendict[str, int]

    def __init__(self, name: str, flags: dict[str, int]):
        super().__init__(name=name)
        object.__setattr__(self, "flags", frozendict(flags))

    def exists(self, flag: str) -> bool:
        """Check if a value is valid for this enum.

        Args:
            value: The value to check.

        Returns:
            True if the value is in this enum's allowed values.
        """
        return flag in self.flags

    @override
    def __str__(self) -> str:
        """Return formatted string representation of the enum."""
        return f"{self.name}[{', '.join(f'{flag} = {value}' for flag, value in self.flags.items())}]"

    @override
    def is_enum(self) -> bool:
        return True


BOOL = Enum("bool", {"FALSE": 0, "TRUE": 1})
