from typing import Protocol

from .KnitResult import KnitResult
from .Pair import Pair


class IKnitter(Protocol):
    def knit(self, pair: Pair) -> KnitResult: ...
