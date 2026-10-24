from __future__ import annotations

from dataclasses import dataclass
from typing import ItemsView, Iterator, Mapping

from frozendict import frozendict

from treehornx.enum_models.Taint.BoolPlus import BoolPlus


Key = tuple[int, int]


@dataclass(frozen=True, slots=True, init=False)
class TaintPtr:
    """taint_ptr[p, i]: the pointer-tainting flag of pointer variable p at the (1-based) frame i of a label.

    Every key is Bottom by default; only the keys with a different value are stored, so two vectors with the
    same flags are equal (and hash the same) however they were built."""

    _taints: frozendict[Key, BoolPlus]

    def __init__(self, taints: Mapping[Key, BoolPlus] | None = None) -> None:
        kept = {key: value for key, value in (taints or {}).items() if value is not BoolPlus.Bottom}
        object.__setattr__(self, "_taints", frozendict(kept))

    def __getitem__(self, key: Key) -> BoolPlus:
        return self._taints.get(key, BoolPlus.Bottom)

    def set(self, key: Key, value: BoolPlus) -> TaintPtr:
        """taint_ptr[key ↦ value]; assigning Bottom removes the key."""
        if value is BoolPlus.Bottom:
            return TaintPtr(self._taints.delete(key)) if key in self._taints else self
        return TaintPtr(self._taints.set(key, value))

    def join(self, key: Key, value: BoolPlus) -> TaintPtr:
        """taint_ptr[key ↦ taint_ptr[key] ⊔ value]"""
        return self.set(key, self[key].join(value))

    def items(self) -> ItemsView[Key, BoolPlus]:
        return self._taints.items()

    def __iter__(self) -> Iterator[Key]:
        return iter(self._taints)

    def __len__(self) -> int:
        return len(self._taints)

    def __contains__(self, key: Key) -> bool:
        return key in self._taints
