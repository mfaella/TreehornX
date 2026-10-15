
from dataclasses import dataclass

from treehornx.enum_models.core.Label import Label

@dataclass(frozen=True, slots=True)
class Pair[F]:
    parent: Label[F]
    child: Label[F]
    j: int
