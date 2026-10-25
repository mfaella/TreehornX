"""Enumerated part of the tainted knitted-trees the tree-shape CHC systems are built on."""

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
class TreeShapeCHC:
    """The final tainted labels and pairs, on top of the enumerated Lab part (whose symbols they reuse)."""

    lab: LabCHC
    engine: TaintingEngine
    labels: list[TaintedLabel]
    pairs: list[Pair[TaintedLabel]]


def tree_shape_from_lab(lab: LabCHC) -> TreeShapeCHC:
    """Enumerates the taints of labels already enumerated, keeping only the final tainted labels and pairs."""
    engine = enumerate_taints(lab)
    final_labels, final_pairs = engine.finals()
    return TreeShapeCHC(lab, engine, labels=list(final_labels), pairs=list(final_pairs))


def build_tree_shape(function: ir.Function, k: int, m: int, n: int) -> TreeShapeCHC:
    """Enumerates the labels and their taints, keeping only the final tainted labels and pairs."""
    return tree_shape_from_lab(build_lab(function, k, m, n))
