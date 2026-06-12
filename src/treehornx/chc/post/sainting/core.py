from __future__ import annotations

from dataclasses import dataclass, field

from frozendict import frozendict

from treehornx.chc.post.tainting.core import TaintedLabel
from treehornx.enum_labels.core.Label import Label

@dataclass(slots=True, frozen=True)
class Q:
    pass

@dataclass(slots=True, frozen=True)
class SaintedLabel:
    label: Label
    state_node: bool | Q
    state_ptr: frozendict[tuple[str, int], bool | Q]

@dataclass(slots=True, frozen=True)
class Initialization:
    tainted_label: TaintedLabel
    sainted_label: SaintedLabel

@dataclass(slots=True, frozen=True)
class AutomataTransition:
    parent: SaintedLabel
    children: frozendict[str, SaintedLabel|None]
    new_parent: SaintedLabel
    states_source: frozendict[str, None|tuple[str, int]|SaintedLabel]

@dataclass(slots=True, frozen=True)
class StartStatePropagation:
    sainted_label: SaintedLabel
    new_sainted_label: SaintedLabel
    propagation_coordinates: tuple[tuple[str, int], ...]

@dataclass(slots=True, frozen=True)
class InternalStatePropagation:
    sainted_sigma: SaintedLabel
    new_sainted_sigma: SaintedLabel
    prpagations: tuple[tuple[str, int, int], ...]

@dataclass(slots=True, frozen=True)
class UpStatePropagation:
    child: SaintedLabel
    parent: SaintedLabel
    new_sainted_sigma2: SaintedLabel
    child_key: int|str
    prpagations: tuple[tuple[str, int, int], ...]

@dataclass(slots=True, frozen=True)
class DownStatePropagation:
    parent: SaintedLabel
    sainted_sigma2: SaintedLabel
    new_sainted_sigma2: SaintedLabel
    child_key: int|str
    prpagations: tuple[tuple[str, int, int], ...]

@dataclass(slots=True, frozen=True)
class Acceptance:
    sainted_label: SaintedLabel

type SaintingStep = Initialization | StartStatePropagation | AutomataTransition | InternalStatePropagation | UpStatePropagation | DownStatePropagation | Acceptance
