"""Enumerated part of the knitted-trees the CHC systems are built on."""

from dataclasses import dataclass
from typing import Iterable, TextIO

from treehornx import ir
from treehornx.chc.clean import clean_clause
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.chc.smt.sexpr import CHCSystem, Clause, Predicate, Transform, write_horn
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab import Lab, LabEngine


def enumerate_labels(function: ir.Function, k: int, m: int, n: int) -> LabEngine:
    assert k == function.node.k, f"k = {k} differs from the number of pointer fields {function.node.k}"
    engine = LabEngine(
        k,
        m,
        n=n,
        function=function,
    )
    engine.fix()
    return engine


@dataclass
class LabCHC:
    """The enumerated part of the knitted-trees and the symbols of their data."""

    engine: LabEngine
    sym: ChcLabUtils
    labels: list[Lab]
    pairs: list[Pair[Lab]]


def build_lab(function: ir.Function, k: int, m: int, n: int) -> LabCHC:
    """Enumerates the labels, keeping only the final labels and pairs."""
    engine = enumerate_labels(function, k, m, n)
    final_labels, final_pairs = engine.finals()
    return LabCHC(engine, ChcLabUtils(function, engine), labels=list(final_labels), pairs=list(final_pairs))


def printing_transform(clean: bool) -> Transform | None:
    """The rewriting applied to the clauses when they are printed: the clean phase, if enabled."""
    return clean_clause if clean else None


def to_system(predicates: Iterable[Predicate], clauses: Iterable[Clause], clean: bool = False) -> CHCSystem:
    """The system of `clauses`, cleaned lazily when printed if `clean`."""
    return CHCSystem(list(predicates), list(clauses), printing_transform(clean))


def write_smt2(clauses: Iterable[Clause], out: TextIO, clean: bool = False) -> None:
    """Writes the system as `CHCSystem.write` does, without holding the clauses together in memory."""
    write_horn(clauses, out, printing_transform(clean))
