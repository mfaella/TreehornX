from collections import defaultdict
from dataclasses import dataclass, field

from typing_extensions import Iterable

from treehornx.chc.utils.terminals_discovery import Pair
from treehornx.enum_labels.core.Label import Label

from .core import SaintedLabel


@dataclass
class SaintDB:
    _labels: set[SaintedLabel] = field(default_factory=set, init=False)
    _pairs: set[Pair[SaintedLabel]] = field(default_factory=set, init=False)
    _parent_index: dict[SaintedLabel, dict[int | str, set[Pair[SaintedLabel]]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(set)), init=False)
    _child_index: dict[SaintedLabel, set[Pair[SaintedLabel]]] = field(default_factory=lambda: defaultdict(set), init=False)

    def labels(self) -> Iterable[SaintedLabel]:
        return iter(self._labels)

    def pairs(self) -> Iterable[Pair[SaintedLabel]]:
        return iter(self._pairs)

    def add_label(self, label: SaintedLabel):
        self._labels.add(label)

    def add_pair(self, sainted_pair: Pair[SaintedLabel]):
        self.add_label(sainted_pair.parent)
        self.add_label(sainted_pair.child)
        self._parent_index[sainted_pair.parent][sainted_pair.child_key].add(sainted_pair)
        self._child_index[sainted_pair.child].add(sainted_pair)
        self._pairs.add(sainted_pair)

    def pairs_by_parent_and_child_key(
        self, parent: SaintedLabel, child_key: int | str
    ) -> Iterable[Pair[SaintedLabel]]:
        return self._parent_index[parent][child_key]

    def pairs_by_child(self, child: SaintedLabel) -> Iterable[Pair[SaintedLabel]]:
        return iter(self._child_index[child])

    def contains_label(self, label: SaintedLabel) -> bool:
        return label in self._labels

    def contains_pair(self, pair: Pair[SaintedLabel]) -> bool:
        return pair in self._pairs
