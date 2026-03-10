from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable, TextIO

from loguru import logger

from .core import Frame, Label, Pair
from .core.dir import Internal


class PairDB:
    def __init__(self):
        self.pairs_db: set[Pair] = set()
        self.leader_index: defaultdict[Label, set[Pair]] = defaultdict(set)
        self.verifier = None
        # self.added_pairs: set[tuple[int, int]] = set()

    def __len__(self) -> int:
        return len(self.pairs_db)

    def add(self, pair: Pair):
        if pair not in self.pairs_db:
            logger.debug(
                f"Adding pair: {{ leader.id: {pair.leader().id}[{len(pair.leader())}], follower.id: {pair.follower().id}[{len(pair.follower())}], child_key: {pair.child_key}, leadership: {pair.leadership} }}"
            )
            self.pairs_db.add(pair)
            self.leader_index[pair.leader()].add(pair)

    def find_by_leader(self, leader: Label) -> Iterable[Pair]:
        return self.leader_index[leader]
