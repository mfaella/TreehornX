from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Up:
    pass


@dataclass(slots=True, frozen=True)
class Internal:
    pass


@dataclass(slots=True, frozen=True)
class Down:
    child: int | None


Dir = Up | Internal | Down


def opposite_dir(d: Dir):
    match d:
        case Up():
            return Down(None)
        case Down(_):
            return Up()
        case Internal():
            return Internal()
