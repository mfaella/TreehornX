from collections import defaultdict
from typing import Iterable

from .core import Label, Pair


class PairDB:
    def __init__(self):
        self.pair_db: set[Pair] = set()
        self.leader_index: defaultdict[Label, set[Pair]] = defaultdict(set)

    def add(self, pair: Pair):
        self.pair_db.add(pair)
        self.leader_index[pair.leader()].add(pair)

    def find_by_leader(self, leader: Label) -> Iterable[Pair]:
        return self.leader_index[leader]
