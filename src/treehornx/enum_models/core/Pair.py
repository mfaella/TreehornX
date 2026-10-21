from dataclasses import dataclass
from typing import Generic, TypeVar

from treehornx.enum_models.core.Label import Label


SN = TypeVar("SN")


@dataclass(frozen=True, slots=True)
class Pair(Generic[SN]):
    parent: SN
    child: SN
    j: int
