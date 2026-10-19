from __future__ import annotations

from dataclasses import dataclass, field
from itertools import islice
from typing import Iterable, overload, override


@dataclass(frozen=True, slots=True)
class Label[F]:
    frame: F
    prefix: Label[F] | None = field(default=None)
    _hash: int = field(init=False)
    _length: int = field(init=False)

    def __post_init__(self) -> None:
        # the prefix hash is cached, so including it is O(1) and keeps labels with different histories apart
        prefix_hash = None if self.prefix is None else self.prefix._hash
        object.__setattr__(self, "_hash", hash((self.frame, prefix_hash)))
        object.__setattr__(self, "_length", 1 + (len(self.prefix) if self.prefix is not None else 0))

    def __iter__(self) -> Iterable[F]:
        return iter(self[1:len(self)])

    def __reversed__(self) -> Iterable[F]:
        return map(lambda label: label.frame, self._naive_iter_prefixes())

    @overload
    def __getitem__(self, index: int) -> F: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[F, ...]: ...

    def __getitem__(self, index: int | slice) -> F | tuple[F, ...]:
        match index:
            case int():
                if not 1 <= index <= len(self):
                    raise IndexError(index)
                return self.cut(index).frame
            case slice():
                assert index.step is None, "slicing with step is not supported"
                start = 1 if index.start is None else index.start
                stop = len(self) if index.stop is None else min(len(self), index.stop)  # inclusive stop
                start, stop = len(self) - stop, len(self) - start + 1
                prefixes_slice = islice(self._naive_iter_prefixes(), start, stop)
                return tuple(reversed(tuple(map(lambda l: l.frame, prefixes_slice))))

    def __len__(self) -> int:
        return self._length

    @override
    def __hash__(self) -> int:
        return self._hash

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Label):
            return NotImplemented
        if not isinstance(other.frame, type(self.frame)): # pyright: ignore[reportUnknownMemberType]
            return NotImplemented
        if self is other:
            return True
        if self.frame != other.frame:
            return False
        if self.prefix is other.prefix: # pyright: ignore[reportUnknownMemberType]
            return True
        return self.prefix == other.prefix # pyright: ignore[reportUnknownMemberType]

    def cut(self, index: int) -> Label[F]:
        return next(islice(self._naive_iter_prefixes(), len(self) - index, None))

    def _naive_iter_prefixes(self) -> Iterable[Label[F]]:
        current: Label[F] | None = self
        while current is not None:
            yield current
            current = current.prefix

    def iter_indexed(self, start: int, stop: int) -> Iterable[tuple[int, F]]:
        return enumerate(self[start:stop], start=start)

    def reversed_iter_indexed(self, start: int, stop: int) -> Iterable[tuple[int, F]]:
        frames = self[start:stop]
        return zip(range(start + len(frames) - 1, start - 1, -1), reversed(frames))
