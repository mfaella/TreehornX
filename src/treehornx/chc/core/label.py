from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from itertools import count
from typing import Any, ClassVar, Iterable

from pysmt.fnode import FNode  # type: ignore

from .frame import Frame

next_label_id = count().__next__


@cache
def _make_label(*frames: Frame) -> Label:
    instance = object.__new__(Label)
    object.__setattr__(instance, "frames", tuple(frames))
    object.__setattr__(instance, "id", next_label_id())

    return instance


@dataclass(frozen=True, slots=True, init=False)
class Label:
    frames: tuple[Frame, ...] = ()
    id: int = field(compare=False, hash=False)

    def __init__(self):
        raise NotImplementedError("Use Label.make() to create Label instances.")

    def extended_with(self, frame: Frame) -> Label:
        return Label.make(*self.frames, frame)

    def __getitem__(self, index: int) -> Frame:
        return self.frames[index]

    def __len__(self) -> int:
        return len(self.frames)

    @classmethod
    def make(cls, *frames: Frame) -> Label:
        return _make_label(*frames)
