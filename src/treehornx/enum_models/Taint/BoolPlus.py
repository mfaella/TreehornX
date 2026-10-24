from __future__ import annotations

from enum import Enum

from typing_extensions import override


class BoolPlus(Enum):
    """The extended Booleans B+ = {⊥, ⊤, ⊤+} of the tainting (⊤+ marks the final trail of the root and its target).

    A value is truthy when it is ⊤(+), i.e. ⊤ or ⊤+."""

    Bottom = 0
    Top = 1
    TopPlus = 2

    def __bool__(self) -> bool:
        return self is not BoolPlus.Bottom

    @override
    def __hash__(self) -> int:
        # Enum hashes the name, a string whose hash changes between runs: the systems would come out in a
        # different order every time
        return hash(self.value)

    def join(self, other: BoolPlus) -> BoolPlus:
        """The least upper bound in ⊥ < ⊤ < ⊤+."""
        return self if self.value >= other.value else other
