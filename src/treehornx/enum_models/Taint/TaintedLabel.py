import weakref
from dataclasses import dataclass
from typing import Callable

from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Taint.BoolPlus import BoolPlus
from treehornx.enum_models.Taint.TaintPtr import TaintPtr


@dataclass(frozen=True, slots=True, weakref_slot=True)
class TaintedLabel:
    """T(σ, taint, taint_ptr): a Lab label with the tainting flags of its node and of its pointer trails."""

    taint_node: BoolPlus
    taint_ptr: TaintPtr
    lab: Lab


TaintedLabelFactory = Callable[[BoolPlus, TaintPtr, Lab], TaintedLabel]
"""Builds a tainted label from its fields; the engine builds every tainted label through one."""

_pool: "weakref.WeakValueDictionary[tuple[BoolPlus, TaintPtr, Lab], TaintedLabel]" = weakref.WeakValueDictionary()


def intern_tainted_label(taint_node: BoolPlus, taint_ptr: TaintPtr, lab: Lab) -> TaintedLabel:
    """The tainted label of these fields, the same instance as long as one is alive."""
    key = (taint_node, taint_ptr, lab)
    label = _pool.get(key)
    if label is None:
        label = TaintedLabel(taint_node, taint_ptr, lab)
        _pool[key] = label
    return label
