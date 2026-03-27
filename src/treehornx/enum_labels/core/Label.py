from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from functools import cached_property
from itertools import islice
from typing import Iterable, cast, overload, override

# from .dir import Down
from .Frame import Frame


@dataclass(frozen=True, slots=True)
class Label:
    frame: Frame
    origin: Label | None = field(default=None)
    _cached_hash: int | None = field(default=None, init=False, hash=False, compare=False)

    def append(self, frame: Frame) -> Label:
        return Label(frame, self)

    def __iter__(self) -> Iterable[Frame]:
        return map(lambda label: label.frame, self.iter_origins())

    def __reversed__(self) -> Iterable[Frame]:
        current: Label | None = self
        while current is not None:
            yield current.frame
            current = current.origin

    @overload
    def __getitem__(self, index: int) -> Frame: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Frame, ...]: ...

    def __getitem__(self, index: int | slice) -> Frame | tuple[Frame, ...]:
        match index:
            case int():
                return self.origin_at(index).frame
            case slice():
                start, stop, step = index.indices(len(self))
                return tuple(self[i] for i in range(start, stop, step))

    def __len__(self) -> int:
        return sum(1 for _ in reversed(self))

    def _compute_cached_hash(self) -> int:
        if self._cached_hash is None:
            hash_value = hash((self.frame, self.origin))
            object.__setattr__(self, "_cached_hash", hash_value)
        return cast(int, self._cached_hash)

    @override
    def __hash__(self) -> int:
        return self._compute_cached_hash()

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Label):
            return NotImplemented
        return self.frame == other.frame and self.origin == other.origin

    def iter_origins(self) -> Iterable[Label]:
        stack: deque[Label] = deque()
        current: Label | None = self
        while current is not None:
            stack.append(current)
            current = current.origin
        while stack:
            yield stack.pop()

    def origin_at(self, index: int) -> Label:
        if index < 0:
            index = len(self) + index
        return next(islice(self.iter_origins(), index, index + 1))
