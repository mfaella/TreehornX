from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import count, islice
from typing import Iterable, override

from treehornx.chc.core.cache_hash import cache_hash

from .frame import Frame

next_label_id = count().__next__


@cache
def _extended_label(label: Label | None, frame: Frame) -> Label:
    instance = object.__new__(Label)
    object.__setattr__(instance, "frame", frame)
    object.__setattr__(instance, "origin", label)
    object.__setattr__(instance, "id", next_label_id())

    return instance


@cache
def _make_label(*frames: Frame) -> Label:
    lab = None
    for f in frames:
        lab = _extended_label(lab, f)
    assert lab is not None
    return lab


@dataclass(frozen=True, init=False)
class Label:
    frame: Frame
    origin: Label | None = field(default=None)
    id: int = field(repr=False, compare=False, hash=False)

    def __init__(self):
        raise NotImplementedError("Use Label.make() to create Label instances.")

    def extended_with(self, frame: Frame) -> Label:
        return _extended_label(self, frame)

    def iter(self) -> Iterable[Frame]:
        current: Label | None = self
        stack: list[Frame] = []
        while current is not None:
            stack.append(current.frame)
            current = current.origin
        while stack:
            yield stack.pop()

    def backward_iter(self) -> Iterable[Frame]:
        current: Label | None = self
        while current is not None:
            yield current.frame
            current = current.origin

    def __getitem__(self, index: int) -> Frame:
        if index < 0:
            index = len(self) + index
        return next(f for f in self.backward_iter() if f.index == index)

    def __len__(self) -> int:
        return sum(1 for _ in self.backward_iter())

    def slice(self, start: int, end: int | None = None) -> Iterable[Frame]:
        return islice(self.iter(), start, end)

    @cached_property
    def hash_value(self) -> int:
        return hash((self.origin, self.frame))

    @override
    def __hash__(self) -> int:
        return self.hash_value

    @classmethod
    def make(cls, *frames: Frame) -> Label:
        return _make_label(*frames)
