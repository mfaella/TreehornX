from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import islice
from typing import Iterable, cast, overload, override

from treehornx.enum_models.core.Dir import Dir

_LABELS_DICT = {}

@dataclass(frozen=True, slots=True)
class Label[F]:
    frame: F
    next: tuple[Dir, int] | None = field(default=None)
    prev: tuple[Dir, int] | None = field(default=None)
    prefix: Label[F] | None = field(default=None)
    _hash: int = field(init=False)
    _length: int = field(init=False)
    _id: int = field(init=False, default=-1)

    def __post_init__(self) -> None:
        # the prefix hash is cached, so including it is O(1) and keeps labels with different histories apart
        prefix_hash = None if self.prefix is None else self.prefix._hash
        object.__setattr__(self, "_hash", hash((self.frame, self.next, self.prev, prefix_hash)))
        object.__setattr__(self, "_length", 1 + (len(self.prefix) if self.prefix is not None else 0))

    @property
    def id(self) -> int:
        """Number given by the engine that registered this label (SymbolicEngine.canonical)."""
        assert self._id >= 0, "label not registered by an engine: use the canonical label returned by the engine"
        return self._id

    def __iter__(self) -> Iterable[F]:
        return iter(self[1:len(self)+1])

    def __reversed__(self) -> Iterable[F]:
        return map(lambda label: label.frame, self.reverse_iter_prefixes())

    @overload
    def __getitem__(self, index: int) -> F: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[F, ...]: ...

    def __getitem__(self, index: int | slice) -> F | tuple[F, ...]:
        match index:
            case int():
                if index < 0:
                    index += len(self) + 1             # -1 -> top frame
                if not 1 <= index <= len(self):
                    raise IndexError(index)
                return self.cut(index).frame
            case slice():
                assert index.step is None, "slicing with step is not supported"
                start = 1 if index.start is None else index.start
                stop = len(self) + 1 if index.stop is None else index.stop  # exclusive
                return tuple(reversed(tuple(map(lambda l: l.frame, self.reverse_iter_prefixes(start, stop - 1)))))

    def __len__(self) -> int:
        return self._length

    @override
    def __hash__(self) -> int:
        return self._hash

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Label):
            return NotImplemented
        if not isinstance(other.frame, type(self.frame)):
            return NotImplemented
        if self is other:
            return True
        if self.frame != other.frame:
            return False
        if self.next != other.next:
            return False
        if self.prev != other.prev:
            return False
        if self.prefix is other.prefix:
            return True
        return self.prefix == other.prefix

    def cut(self, index: int) -> Label[F]:
        return next(islice(self._naive_iter_prefixes(), len(self) - index, None))

    def reverse_iter_prefixes(self, start: int|None = None, stop: int|None = None) -> Iterable[Label[F]]:
        """

        Args:
            start: inclusive, 1-based index of the lowest prefix to return (default: 1)
            stop: inclusive, 1-based index of the highest prefix to return (default: len(self))

        Returns:
            An iterator over the prefixes of this label, in reverse order (from top to bottom).
            Empty when start > stop (like an empty slice)."""
        start = 1 if start is None else start
        stop = len(self) if stop is None else stop
        assert start >= 1, f"start={start} is out of bounds"
        assert stop <= len(self), f"stop={stop} is out of bounds"
        i = len(self)
        curr = self
        while i > stop:
            i -= 1
            curr = curr.prefix
        while i >= start:
            yield curr
            i -= 1
            curr = curr.prefix

    def reverse_iter_frames(self, start: int|None = None, stop: int|None = None) -> Iterable[tuple[int, F]]:
        i = stop if stop is not None else len(self)
        prefixes_iter = self.reverse_iter_prefixes(start, stop)
        for prefix in prefixes_iter:
            yield i, prefix.frame
            i -= 1

    def _naive_iter_prefixes(self) -> Iterable[Label[F]]:
        current: Label[F] | None = self
        while current is not None:
            yield current
            current = current.prefix
