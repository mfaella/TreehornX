from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from itertools import product
from typing import Any

from frozendict import frozendict
from typing_extensions import override

from treehornx.chc.utils import end_of_lace
from treehornx.enum_labels.core.Label import Label


@dataclass
class TaintedLabelFactory:
    _cache: dict[tuple[Label, bool, frozendict[tuple[str, int], bool]], TaintedLabel] = field(
        init=False, default_factory=dict
    )

    def create(self, label: Label, taint_node: bool, taint_ptr: frozendict[tuple[str, int], bool]) -> TaintedLabel:
        key = (label, taint_node, taint_ptr)
        if key not in self._cache:
            tainted_label = TaintedLabel(label=label, taint_node=taint_node, taint_ptr=taint_ptr)
            object.__setattr__(tainted_label, "_factory", self)
            self._cache[key] = tainted_label
        return self._cache[key]

    def replace(
        self,
        tainted_label: TaintedLabel,
        label: Label | None = None,
        taint_node: bool | None = None,
        taint_ptr: frozendict[tuple[str, int], bool] | None = None,
    ) -> TaintedLabel:
        new_label = label if label is not None else tainted_label.label
        new_taint_node = taint_node if taint_node is not None else tainted_label.taint_node
        new_taint_ptr = taint_ptr if taint_ptr is not None else tainted_label.taint_ptr
        return self.create(new_label, new_taint_node, new_taint_ptr)


@dataclass(frozen=True)
class TaintedLabel:
    label: Label
    taint_node: bool
    taint_ptr: frozendict[tuple[str, int], bool]
    _factory: TaintedLabelFactory | None = field(init=False, default=None, compare=False, hash=False)

    @cached_property
    def _computed_hash(self):
        return hash((self.label, self.taint_node, self.taint_ptr))

    @override
    def __hash__(self):
        return self._computed_hash

    @override
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TaintedLabel):
            return NotImplemented
        if self._factory and self._factory is other._factory:
            return self is other
        return (self.label, self.taint_node, self.taint_ptr) == (other.label, other.taint_node, other.taint_ptr)


@dataclass
class TaintedPairFactory:
    _cache: dict[tuple[TaintedLabel, TaintedLabel, int | str], TaintedPair] = field(init=False, default_factory=dict)

    def create(self, parent: TaintedLabel, child: TaintedLabel, child_key: int | str) -> TaintedPair:
        key = (parent, child, child_key)
        if key not in self._cache:
            tainted_pair = TaintedPair(parent=parent, child=child, child_key=child_key)
            object.__setattr__(tainted_pair, "_factory", self)
            self._cache[key] = tainted_pair
        return self._cache[key]

    def replace(
        self,
        pair: TaintedPair,
        parent: TaintedLabel | None = None,
        child: TaintedLabel | None = None,
        child_key: int | str | None = None,
    ) -> TaintedPair:
        new_parent = parent if parent is not None else pair.parent
        new_child = child if child is not None else pair.child
        new_child_key = child_key if child_key is not None else pair.child_key
        return self.create(new_parent, new_child, new_child_key)


@dataclass(frozen=True)
class TaintedPair:
    parent: TaintedLabel
    child: TaintedLabel
    child_key: int | str
    _factory: TaintedPairFactory | None = field(init=False, default=None, compare=False, hash=False)

    @cached_property
    def _computed_hash(self):
        return hash((self.parent, self.child, self.child_key))

    @override
    def __hash__(self):
        return self._computed_hash

    @override
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TaintedPair):
            return NotImplemented
        if self._factory and self._factory is other._factory:
            return self is other
        return (self.parent, self.child, self.child_key) == (other.parent, other.child, other.child_key)


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
