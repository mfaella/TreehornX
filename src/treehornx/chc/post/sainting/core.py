from __future__ import annotations

from dataclasses import dataclass, field

from frozendict import frozendict

from treehornx.chc.post.tainting.core import BoolPlus, TaintedLabel
from treehornx.enum_labels.core.Label import Label

@dataclass(slots=True, frozen=True)
class Q:
    pass

@dataclass(slots=True, frozen=True)
class SaintedLabel:
    label: Label
    state_node: BoolPlus | Q
    state_struct_children: frozendict[str, BoolPlus | Q]
    state_ptr: frozendict[tuple[str, int], BoolPlus | Q]

@dataclass(slots=True, frozen=True)
class Initialization:
    tainted_label: TaintedLabel
    sainted_label: SaintedLabel

@dataclass(slots=True, frozen=True)
class AutomataTransition:
    parent: SaintedLabel
    new_parent: SaintedLabel
    states_source: frozendict[str, None|tuple[str, int]|str]

@dataclass(slots=True, frozen=True)
class StartStatePropagation:
    sainted_label: SaintedLabel
    new_sainted_label: SaintedLabel
    propagation_coordinates: tuple[str, int]

@dataclass(slots=True, frozen=True)
class InternalStatePropagation:
    sainted_sigma: SaintedLabel
    new_sainted_sigma: SaintedLabel
    prpagations: tuple[str, int, int]

@dataclass(slots=True, frozen=True)
class UpStatePropagation:
    child: SaintedLabel
    parent: SaintedLabel
    new_parent: SaintedLabel
    child_key: int|str
    prpagations: tuple[str, int, int]

@dataclass(slots=True, frozen=True)
class DownStatePropagation:
    parent: SaintedLabel
    child: SaintedLabel
    new_child: SaintedLabel
    child_key: int|str
    prpagations: tuple[str, int, int]

@dataclass(slots=True, frozen=True)
class StructuralChildUpload:
    parent: SaintedLabel
    child: SaintedLabel
    new_parent: SaintedLabel
    child_key: str

@dataclass(slots=True, frozen=True)
class NonEmptyAcceptance:
    sainted_label: SaintedLabel

@dataclass(slots=True, frozen=True)
class EmptyAcceptance:
    sainted_label: SaintedLabel

type SaintingStep = Initialization | StartStatePropagation | StructuralChildUpload | AutomataTransition | InternalStatePropagation | UpStatePropagation | DownStatePropagation | NonEmptyAcceptance | EmptyAcceptance
