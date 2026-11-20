"""Parts shared by the analyses: `ConstrTLab` and `symbol_generator`."""

from __future__ import annotations

from typing import Iterator

from treehornx import smt
from treehornx.analysis.commons.ConstrTLab import ConstrTLab
from treehornx.analysis.constraints.symbols import Symbol


def symbol_generator(n: int, type: smt.Type) -> Iterator[Symbol]:
    """`n` symbols of type `type` with no role: `I1 .. In` for `Int`, `B1 .. Bn` for `Bool`."""
    prefix = "I" if type is smt.Type.Int else "B"
    for i in range(1, n + 1):
        yield Symbol.make(base_name=f"{prefix}{i}", type=type, role=None)


__all__ = ["ConstrTLab", "symbol_generator"]
