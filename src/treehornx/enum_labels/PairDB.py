from collections import defaultdict
from typing import Iterable, Iterator

from .core import Label
from .knitter.Pair import Pair


class PairDB:
    def __init__(self):
        self.pairs_db: set[Pair] = set()
        self.leader_index: defaultdict[Label, set[Pair]] = defaultdict(set)
        self.verifier = None
        # self.added_pairs: set[tuple[int, int]] = set()

    def __len__(self) -> int:
        return len(self.pairs_db)

    def __iter__(self) -> Iterator[Pair]:
        return iter(self.pairs_db)

    def add(self, pair: Pair):
        if pair not in self.pairs_db:
            self.pairs_db.add(pair)
            self.leader_index[pair.leader()].add(pair)

    def find_by_leader(self, leader: Label) -> Iterable[Pair]:
        return self.leader_index[leader]
