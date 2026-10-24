"""Enumerated part of the tainted knitted-trees the postcondition CHC systems are built on."""

from dataclasses import dataclass

from treehornx import ir
from treehornx.chc.Lab.system import LabCHC, build_lab
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Taint import TaintedLabel, TaintingEngine


def enumerate_taints(lab: LabCHC) -> TaintingEngine:
    engine = TaintingEngine(lab.engine)
    engine.fix()
    return engine


@dataclass
class PostCHC:
    """The final tainted labels and pairs, on top of the enumerated Lab part (whose symbols they reuse)."""

    lab: LabCHC
    engine: TaintingEngine
    labels: list[TaintedLabel]
    pairs: list[Pair[TaintedLabel]]


def post_from_lab(lab: LabCHC) -> PostCHC:
    """Enumerates the taints of labels already enumerated, keeping only the final tainted labels and pairs."""
    engine = enumerate_taints(lab)
    final_labels, final_pairs = engine.finals()
    return PostCHC(lab, engine, labels=list(final_labels), pairs=list(final_pairs))


def build_post(function: ir.Function, k: int, m: int, n: int) -> PostCHC:
    """Enumerates the labels and their taints, keeping only the final tainted labels and pairs."""
    return post_from_lab(build_lab(function, k, m, n))
