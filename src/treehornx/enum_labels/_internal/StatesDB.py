from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from treehornx.enum_labels._internal.knitter.Pair import LeadershipKind, Pair
from treehornx.enum_labels.core.Frame import Frame
from treehornx.enum_labels.core.Label import Label


@dataclass(slots=True)
class _LabelInfo:
    instance: Label
    ancestors: set[Label] = field(init=False, default_factory=set)
    extensions: set[Label] = field(init=False, default_factory=set)
    is_endless_loop_pivot: bool = field(init=False, default=False)
    is_connection_label: bool = field(init=False, default=False)
    led_pairs: set[Pair] = field(init=False, default_factory=set)


@dataclass(slots=True)
class _PairInfo:
    instance: Pair


@dataclass
class StatesDB:
    _labels: dict[Label, _LabelInfo] = field(init=False, default_factory=dict)
    _pairs: dict[Pair, _PairInfo] = field(init=False, default_factory=dict)

    def get_ancestors(self, lab: Label) -> Iterable[Label]:
        return self._labels[lab].ancestors

    def get_extensions(self, lab: Label) -> Iterable[Label]:
        return self._labels[lab].extensions

    def get_connection_extensions(self, lab: Label) -> Iterable[Label]:
        return (ext for ext in self._labels[lab].extensions if self._labels[ext].is_connection_label)

    def is_endless_loop_pivot(self, lab: Label) -> bool:
        return self._labels[lab].is_endless_loop_pivot

    def is_connection_label(self, lab: Label) -> bool:
        return self._labels[lab].is_connection_label

    def find_all_labels(self) -> Iterable[Label]:
        return iter(self._labels)

    def find_labels_by_origin(self, origin: Label) -> Iterable[Label]:
        return iter(self._labels[origin].extensions)

    def labels_count(self) -> int:
        return len(self._labels)

    # read pairs functions

    def find_all_pairs(self) -> Iterable[Pair]:
        return iter(self._pairs)

    def find_pairs_by_leader(self, lab: Label) -> Iterable[Pair]:
        return iter(self._labels[lab].led_pairs)

    def pairs_count(self) -> int:
        return len(self._pairs)

    # write labels functions

    def _save_label(self, lab: Label) -> Label:
        if lab not in self._labels:
            self._labels[lab] = _LabelInfo(lab)
            if lab.origin is not None:
                self._labels[lab.origin].extensions.add(lab)
            return lab
        else:
            return self._labels[lab].instance

    def make_label(self, origin: Label | None, frame: Frame) -> Label:
        lab = Label(origin=origin, frame=frame)
        return self._save_label(lab)

    def add_label(self, lab: Label):
        self._save_label(lab)

    def add_ancestor(self, lab: Label, ancestor: Label):
        self._labels[lab].ancestors.add(ancestor)

    def set_endless_loop_pivot(self, lab: Label, is_pivot: bool = True):
        self._labels[lab].is_endless_loop_pivot = is_pivot

    def set_connection_label(self, lab: Label, is_connection: bool = True):
        self._labels[lab].is_connection_label = is_connection

    # write pairs functions

    def _save_pair(self, pair: Pair) -> Pair:
        if pair not in self._pairs:
            self._pairs[pair] = _PairInfo(pair)
            self._labels[pair.leader()].led_pairs.add(pair)
            return pair
        else:
            return self._pairs[pair].instance

    def make_pair(self, parent: Label, child: Label, child_key: str | int, leadership: LeadershipKind) -> Pair:
        pair = Pair(parent=parent, child=child, child_key=child_key, leadership=leadership)
        pair = self._save_pair(pair)
        return pair

    def add_pair(self, pair: Pair):
        if pair not in self._pairs:
            self._pairs[pair] = _PairInfo(pair)
            self._labels[pair.leader()].led_pairs.add(pair)
