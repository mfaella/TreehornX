from collections import defaultdict
from dataclasses import dataclass, field

from typing_extensions import Iterable

from treehornx.chc.post.tainting import TaintedLabel, TaintedPair


@dataclass
class TaintDB:
    _labels: set[TaintedLabel] = field(default_factory=set, init=False)
    _pairs: set[TaintedPair] = field(default_factory=set, init=False)
    _participation_index: defaultdict[TaintedLabel, list[TaintedPair]] = field(
        default_factory=lambda: defaultdict(list), init=False
    )

    def labels(self) -> Iterable[TaintedLabel]:
        return iter(self._labels)

    def pairs(self) -> Iterable[TaintedPair]:
        return iter(self._pairs)

    def add_label(self, label: TaintedLabel):
        self._labels.add(label)

    def add_pair(self, pair: TaintedPair):
        if pair in self._pairs:
            return
        self.add_label(pair.parent)
        self.add_label(pair.child)
        self._pairs.add(pair)
        self._participation_index[pair.parent].append(pair)
        self._participation_index[pair.child].append(pair)

    def get_involved_pairs(self, label: TaintedLabel) -> Iterable[TaintedPair]:
        return iter(self._participation_index[label])

    def contains_label(self, label: TaintedLabel) -> bool:
        return label in self._labels

    def contains_pair(self, pair: TaintedPair) -> bool:
        return pair in self._pairs
