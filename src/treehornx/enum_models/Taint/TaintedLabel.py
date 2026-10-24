from dataclasses import dataclass

from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Taint.BoolPlus import BoolPlus
from treehornx.enum_models.Taint.TaintPtr import TaintPtr


@dataclass(frozen=True, slots=True)
class TaintedLabel:
    """T(σ, taint, taint_ptr): a Lab label with the tainting flags of its node and of its pointer trails."""

    taint_node: BoolPlus
    taint_ptr: TaintPtr
    lab: Lab
