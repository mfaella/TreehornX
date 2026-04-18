from dataclasses import dataclass
from itertools import product

from frozendict import frozendict

from treehornx.chc.utils import end_of_lace
from treehornx.enum_labels.core.Label import Label


@dataclass(slots=True, frozen=True)
class TaintedLabel:
    label: Label
    taint_node: bool
    taint_ptr: frozendict[tuple[str, int], bool]


@dataclass(slots=True, frozen=True)
class TaintedPair:
    parent: TaintedLabel
    child: TaintedLabel
    child_key: int | str


@dataclass(slots=True, frozen=True)
class TaintingInitialization:
    tainted_label: TaintedLabel


@dataclass(slots=True, frozen=True)
class LookingForRoot:
    tainted_label: TaintedLabel


@dataclass(slots=True, frozen=True)
class StructuralChildTainting:
    parent: TaintedLabel
    child: TaintedLabel
    new_child: TaintedLabel
    child_key: int | str


@dataclass(slots=True, frozen=True)
class StartOfPointerTainting:
    lab: TaintedLabel
    new_lab: TaintedLabel


@dataclass(slots=True, frozen=True)
class InternalTaintingPropagation:
    lab: TaintedLabel
    new_lab: TaintedLabel


@dataclass(slots=True, frozen=True)
class UpTaintingPropagation:
    parent: TaintedLabel
    child: TaintedLabel
    child_key: int | str
    new_parent: TaintedLabel


@dataclass(slots=True, frozen=True)
class DownTaintingPropagation:
    parent: TaintedLabel
    child: TaintedLabel
    child_key: int | str
    new_child: TaintedLabel


@dataclass(slots=True, frozen=True)
class PointerTaintingEnd:
    lab: TaintedLabel
    new_lab: TaintedLabel


type TaintingStep = (
    TaintingInitialization
    | LookingForRoot
    | StructuralChildTainting
    | StartOfPointerTainting
    | InternalTaintingPropagation
    | UpTaintingPropagation
    | DownTaintingPropagation
    | PointerTaintingEnd
)


def init_tainted_label(lab: Label, root_name: str) -> TaintedLabel:
    lab_len = len(lab)
    tainted_ptr: frozendict[tuple[str, int], bool] = frozendict(
        {(ptr, i): False for i, ptr in product(range(1, lab_len), lab.frame.isnil.keys())}
    )
    if end_of_lace(lab) and not lab.frame.isnil[root_name]:
        tainted_ptr = tainted_ptr.set((root_name, lab_len - 1), True)
    return TaintedLabel(label=lab, taint_node=False, taint_ptr=tainted_ptr)
