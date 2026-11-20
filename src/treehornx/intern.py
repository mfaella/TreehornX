"""Interning (hash-consing) of immutable classes.

`@intern` gives a class the static method `make(**fields)`, the only way to build an instance: it returns the
instance alive with the same fields, or a new one. The constructor raises, so no instance escapes the pool.

* `make` takes keyword arguments only, the parameters of `__init__`; the missing ones take their defaults.
* The key of an instance is the tuple of its field values in parameter order, followed by their types: the order of
  the keyword arguments does not matter, and values that are equal across types (`True == 1`) do not share an
  instance.
* The pool is weak: an instance leaves it when it is no longer referenced. `reset_pool(cls)` empties it,
  `pool_of(cls)` returns it.
* An optional static method `__intern_args__(**fields) -> dict` normalizes the arguments before the key is built
  (e.g. turns an iterable into a tuple).

Pyright cannot see the method added by the decorator: a class declares the signature of `make` under
`TYPE_CHECKING`.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, NoReturn, TypeVar
from weakref import WeakValueDictionary


T = TypeVar("T")

_RESET = "__intern_reset__"
_POOL = "__intern_pool__"


def intern(cls: type[T]) -> type[T]:
    init = cls.__init__
    params = [(p.name, p.default) for p in list(inspect.signature(init).parameters.values())[1:]]
    names = frozenset(name for name, _ in params)
    normalize: Callable[..., dict[str, Any]] | None = getattr(cls, "__intern_args__", None)
    pool: WeakValueDictionary[tuple[Any, ...], T] = WeakValueDictionary()

    def raising_init(self: T, *args: Any, **kwargs: Any) -> NoReturn:
        raise RuntimeError(f"using the constructor of {cls.__name__} breaks interning, use {cls.__name__}.make")

    def eq(left: T, right: T) -> bool:
        return left is right

    def key(values: list[Any]) -> tuple[Any, ...]:
        return (*values, *map(type, values))

    def make(**kwargs: Any) -> T:
        if normalize is not None:
            kwargs = normalize(**kwargs)
        if not names.issuperset(kwargs):
            raise TypeError(f"{cls.__name__}.make got unexpected arguments {sorted(set(kwargs) - names)}")
        values: list[Any] = []
        for name, default in params:
            if name in kwargs:
                values.append(kwargs[name])
            elif default is not inspect.Parameter.empty:
                values.append(default)
            else:
                raise TypeError(f"{cls.__name__}.make is missing the argument {name!r}")
        k = key(values)
        instance = pool.get(k)
        if instance is None:
            instance = cls.__new__(cls)
            init(instance, **kwargs)
            pool[k] = instance
        return instance

    def reset() -> None:
        pool.clear()

    setattr(cls, "__init__", raising_init)
    setattr(cls, "__eq__", eq)
    setattr(cls, "make", staticmethod(make))
    setattr(cls, _RESET, staticmethod(reset))
    setattr(cls, _POOL, pool)
    return cls


def pool_of(cls: type[T]) -> WeakValueDictionary[tuple[Any, ...], T]:
    """The pool of the interned class `cls` (for inspection, e.g. by the tests)."""
    return getattr(cls, _POOL)


def reset_pool(cls: type[T]) -> None:
    """Empties the pool of the interned class `cls`: instances alive stay valid but are no longer returned by `make`."""
    getattr(cls, _RESET)()
