import gc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

import pytest

from treehornx.intern import intern, pool_of, reset_pool


@intern
@dataclass(frozen=True, slots=True, weakref_slot=True)
class Point:
    x: object
    y: object = 0

    if TYPE_CHECKING:

        @staticmethod
        def make(*, x: object, y: object = 0) -> "Point": ...


@intern
@dataclass(frozen=True, slots=True, weakref_slot=True)
class Row:
    cells: tuple[int, ...]

    if TYPE_CHECKING:

        @staticmethod
        def make(*, cells: Iterable[int]) -> "Row": ...

    @staticmethod
    def __intern_args__(cells: Iterable[int]) -> dict[str, Any]:
        return {"cells": tuple(cells)}


def test_constructor_raises() -> None:
    with pytest.raises(RuntimeError):
        Point(1, 2)


def test_make_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        Point.make(1, 2)  # type: ignore[misc]


def test_same_fields_same_instance() -> None:
    assert Point.make(x=1, y=2) is Point.make(y=2, x=1)
    assert Point.make(x=1) is Point.make(x=1, y=0)
    assert Point.make(x=1, y=2) is not Point.make(x=2, y=1)


def test_types_are_part_of_the_key() -> None:
    assert Point.make(x=True) is not Point.make(x=1)
    assert Point.make(x=True).x is True and Point.make(x=1).x == 1


def test_arguments_are_normalized() -> None:
    assert Row.make(cells=[1, 2]) is Row.make(cells=(1, 2))


def test_unknown_and_missing_arguments() -> None:
    with pytest.raises(TypeError):
        Point.make(x=1, z=2)  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError):
        Point.make()  # pyright: ignore[reportCallIssue]


def test_pool_is_weak_and_resettable() -> None:
    kept = Point.make(x="kept")
    Point.make(x="dropped")
    gc.collect()
    assert all(p.x != "dropped" for p in pool_of(Point).values())
    other = Point.make(x="other")
    reset_pool(Point)
    assert Point.make(x="kept") is not kept
    assert Point.make(x="other") is not other
