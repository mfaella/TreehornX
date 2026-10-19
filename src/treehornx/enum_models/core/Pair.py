
from dataclasses import dataclass

from treehornx.enum_models.core.Label import Label

@dataclass(frozen=True, slots=True)
class Pair[SN]:
    parent: SN
    child: SN
    j: int
