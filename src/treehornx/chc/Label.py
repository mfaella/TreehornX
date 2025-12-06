from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from itertools import islice
from typing import ClassVar, Iterable

from pysmt.fnode import FNode

from .Frame import Frame


@cache
def _make_label(prev: Label | None, frame: Frame) -> Label:
    instance = object.__new__(Label)
    object.__setattr__(instance, "prev", prev)
    object.__setattr__(instance, "frame", frame)
    return instance


@dataclass(frozen=True, slots=True, init=False)
class Label:
    prev: Label | None
    frame: Frame
    constraints: FNode | None = field(default=None, compare=False, hash=False)

    def __init__(self):
        raise NotImplementedError("Use Label.make() to create Label instances.")

    def extended(self, frame: Frame) -> Label:
        frame = frame.updated(index=self.frame.index + 1)
        return Label.make(self, frame)

    def __reversed__(self) -> Iterable[Frame]:
        current: Label | None = self
        while current is not None:
            yield current.frame
            current = current.prev

    def __iter__(self) -> Iterable[Frame]:
        if self.prev is None:
            yield self.frame
        else:
            yield from iter(self.prev)
            yield self.frame

    def __getitem__(self, index: int) -> Frame:
        return next(islice(self.reverse_iterator(), index))

    def __len__(self) -> int:
        return sum(1 for _ in self.reverse_iterator())

    @classmethod
    def make(cls, prev: Label | None, frame: Frame) -> Label:
        return _make_label(prev, frame)
