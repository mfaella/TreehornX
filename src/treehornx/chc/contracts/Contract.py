
from itertools import pairwise
from typing import Callable
from dataclasses import dataclass

from pysmt.fnode import FNode
import pysmt.shortcuts as smt

from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.post.tainting.core import TaintedLabel
from treehornx.chc.psi import error_psiF
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.enum_labels.core.Event import FieldAssignP
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.function import Function
from treehornx.ir.instructions import FieldAssignExpr


@dataclass(slots=True, frozen=True)
class Contract[T]:
    failure_check: Callable[[T, CHCFragmentFactory, str], FNode]

def read_only_failure_check_on_Label(label: Label, fragment_factory: CHCFragmentFactory, prefix: str = "") -> FNode:

    for (fprev, fsucc) in pairwise(iter(label)):
        if fprev.active != fsucc.active:
            return smt.TRUE()
        if fprev.enum_fields != fsucc.enum_fields:
            return smt.TRUE()
    for frame in iter(label):
        if any(isinstance(ev, FieldAssignP) for ev in frame.events):
            return smt.TRUE()
    constraints: list[FNode] = []
    while label.origin is not None:
        for var in fragment_factory.data_fields:
            left = fragment_factory.field_symbol(var, label.origin, prefix)
            right = fragment_factory.field_symbol(var, label, prefix)
            constraints.append(smt.NotEquals(left, right))
        label = label.origin
    return smt.Or(*constraints) if constraints else smt.FALSE()

def read_only_failure_check_on_TaintedLabel(tainted_label: TaintedLabel, fragment_factory: CHCFragmentFactory, prefix: str = "") -> FNode:
    lab = tainted_label.label
    return read_only_failure_check_on_Label(lab, fragment_factory, prefix)

def read_only_contract() -> Contract[TaintedLabel]:
    return Contract[TaintedLabel](read_only_failure_check_on_TaintedLabel)
