from dataclasses import dataclass


@dataclass(frozen=True)
class NOP:
    pass


@dataclass(frozen=True)
class ERR:
    pass


@dataclass(frozen=True)
class OOM:
    pass


@dataclass(frozen=True)
class LOF:
    """label overflow"""

    pass


@dataclass(slots=True, frozen=True)
class FieldAssignP:
    pfield: str
    p: str | None


@dataclass(slots=True, frozen=True)
class Here:
    p: str


@dataclass(slots=True, frozen=True)
class FieldHere:
    pfield: str


@dataclass(slots=True, frozen=True)
class Rewind:
    i: int


@dataclass(slots=True, frozen=True)
class Rewind2:
    i: int
    p: str


@dataclass(frozen=True)
class Exit:
    pass


Event = NOP | OOM | ERR | FieldAssignP | Here | Rewind | Rewind2 | Exit | LOF | FieldHere
