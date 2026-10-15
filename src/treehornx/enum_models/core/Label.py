from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import islice
from typing import Iterable, cast, overload, override

from treehornx.enum_models.core.Dir import Dir

_LABELS_DICT = {}

def make_label[FT](frame: FT, next: tuple[Dir, int] | None = None, prev: tuple[Dir, int] | None = None, prefix: Label[FT] | None = None) -> Label[FT]:
    global _LABELS_DICT
    key = (frame, next, prev, prefix)
    if key not in _LABELS_DICT:
        label = cast(Label[FT], object.__new__(Label))
        object.__setattr__(label, "frame", frame)
        object.__setattr__(label, "next", next)
        object.__setattr__(label, "prev", prev)
        object.__setattr__(label, "prefix", prefix)
        object.__setattr__(label, "_hash", hash(key))
        length = 1 if prefix is None else len(prefix) + 1
        object.__setattr__(label, "_length", length)
        object.__setattr__(label, "id", len(_LABELS_DICT))
        _LABELS_DICT[key] = label
    return _LABELS_DICT[key]

@dataclass(frozen=True, slots=True)
class Label[F]:
    frame: F
    next: tuple[Dir, int] | None
    prev: tuple[Dir, int] | None
    prefix: Label[F] | None = field(default=None)
    _hash: int = field(init=False)
    _length: int = field(init=False)
    id: int = field(init=False)

    def __post_init__(self) -> None:
        raise ValueError("use the make function")

    def __iter__(self) -> Iterable[F]:
        return reversed(list(reversed(self)))

    def __reversed__(self) -> Iterable[F]:
        return map(lambda label: label.frame, self._iter_prefixes())

    @overload
    def __getitem__(self, index: int) -> F: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[F, ...]: ...

    def __getitem__(self, index: int | slice) -> F | tuple[F, ...]:
        frames = tuple(iter(self))                     # frames[p - 1] is position p
        match index:
            case int():
                if index < 0:
                    index += len(self) + 1             # -1 -> top frame
                if not 1 <= index <= len(self):
                    raise IndexError(index)
                return frames[index - 1]
            case slice():
                start = 1 if index.start is None else index.start
                stop = len(self) + 1 if index.stop is None else index.stop
                if start < 0:
                    start += len(self) + 1
                if stop < 0:
                    stop += len(self) + 1
                return frames[start - 1 : stop - 1 : index.step or 1]

    def __len__(self) -> int:
        return self._length

    def _compute_cached_hash(self) -> int:
        return self._hash

    @override
    def __hash__(self) -> int:
        return self._compute_cached_hash()

    @override
    def __eq__(self, other: object) -> bool:
        return self is other

    def cut(self, index: int) -> Label[F]:
        return next(islice(self._iter_prefixes(), len(self) - index, None))

    def _iter_prefixes(self) -> Iterable[Label[F]]:
        current: Label[F] | None = self
        while current is not None:
            yield current
            current = current.prefix
