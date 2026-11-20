"""The values of the tainting (POPL27, Sec. 6): the extended Booleans `BoolPlus` and the pointer-tainting flags
`TaintPtr` of a label."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ItemsView, Iterator, Mapping

from frozendict import frozendict
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


TaintPtrCoord = tuple[int, int]


@dataclass(frozen=True, slots=True, init=False)
class TaintPtr:
    """taint_ptr[p, i]: the pointer-tainting flag of pointer variable p at the (1-based) frame i of a label.

    Every key is Bottom by default; only the keys with a different value are stored, so two vectors with the
    same flags are equal (and hash the same) however they were built."""

    _taints: frozendict[TaintPtrCoord, BoolPlus]

    def __init__(self, taints: Mapping[TaintPtrCoord, BoolPlus] | None = None) -> None:
        kept = {key: value for key, value in (taints or {}).items() if value is not BoolPlus.Bottom}
        object.__setattr__(self, "_taints", frozendict(kept))

    def __getitem__(self, key: TaintPtrCoord) -> BoolPlus:
        return self._taints.get(key, BoolPlus.Bottom)

    def set(self, key: TaintPtrCoord, value: BoolPlus) -> TaintPtr:
        """taint_ptr[key ↦ value]; assigning Bottom removes the key."""
        if value is BoolPlus.Bottom:
            return TaintPtr(self._taints.delete(key)) if key in self._taints else self
        return TaintPtr(self._taints.set(key, value))

    def join(self, key: TaintPtrCoord, value: BoolPlus) -> TaintPtr:
        """taint_ptr[key ↦ taint_ptr[key] ⊔ value]"""
        return self.set(key, self[key].join(value))

    def items(self) -> ItemsView[TaintPtrCoord, BoolPlus]:
        return self._taints.items()

    def __iter__(self) -> Iterator[TaintPtrCoord]:
        return iter(self._taints)

    def __len__(self) -> int:
        return len(self._taints)

    def __contains__(self, key: TaintPtrCoord) -> bool:
        return key in self._taints
