"""Test helper: empties the pools of the interned terms and CHC nodes.

The pools are weak, so a test that wants a known state (empty pools) calls `reset_env()`. `TRUE` and `FALSE` stay in
the pool of `Constant`, so they remain canonical. `snapshot()` and `restore()` give the pools back at the end of the
test, so the module-level terms of the other tests stay canonical.
"""

from __future__ import annotations

from typing import Any

from treehornx.smt.sexpr import Application, Clause, Predicate
from treehornx.analysis.constraints.symbols import Symbol
from treehornx.intern import pool_of
from treehornx.smt import FALSE, TRUE, Constant, OpExpr, Var


POOLED: tuple[type[Any], ...] = (Constant, Var, OpExpr, Symbol, Predicate, Application, Clause)

Snapshot = dict[type[Any], dict[tuple[Any, ...], Any]]


def snapshot() -> Snapshot:
    """The instances alive in each pool (strong references, so they stay alive until `restore`)."""
    return {cls: dict(pool_of(cls).items()) for cls in POOLED}


def restore(saved: Snapshot) -> None:
    """Empties the pools and puts the instances of `saved` back."""
    for cls, items in saved.items():
        pool = pool_of(cls)
        pool.clear()
        pool.update(items)


def reset_env() -> None:
    """Empties the pools; terms built before the call are no longer equal to the ones built after it."""
    for cls in POOLED:
        pool = pool_of(cls)
        kept = {key: value for key, value in pool.items() if value is TRUE or value is FALSE}
        pool.clear()
        pool.update(kept)
