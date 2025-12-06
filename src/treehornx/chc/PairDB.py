from typing import Iterable

from .Label import Label
from .Pair import Pair


class PairDB:
    def __init__(self):
        self.pair_db: set[Pair] = set()

    def add(self, pair: Pair):
        self.pair_db.add(pair)

    def find_by(
        self, leader: Label | None = None, follower: Label | None = None, child_index: int | None = None
    ) -> Iterable[Pair]:
        for pair in self.pair_db:
            if leader is not None and pair.leader() != leader:
                continue
            if follower is not None and pair.follower() != follower:
                continue
            if child_index is not None and pair.child_index != child_index:
                continue
            yield pair
