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


@dataclass(slots=True, frozen=True)
class FieldAssignP:
    pfield: int
    p: int | None


@dataclass(slots=True, frozen=True)
class Here:
    p: int


@dataclass(slots=True, frozen=True)
class Rewind:
    i: int


@dataclass(slots=True, frozen=True)
class Rewind2:
    i: int
    p: int


@dataclass(frozen=True)
class Exit:
    pass


Event = NOP | OOM | ERR | FieldAssignP | Here | Rewind | Rewind2 | Exit
