from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Up:
    pass


@dataclass(slots=True, frozen=True)
class Internal:
    pass


@dataclass(slots=True, frozen=True)
class Down:
    child: str | int


Dir = Up | Internal | Down


def are_opposite_directions(dir1: Dir, dir2: Dir) -> bool:
    return (
        (isinstance(dir1, Up) and isinstance(dir2, Down))
        or (isinstance(dir1, Down) and isinstance(dir2, Up))
        or (isinstance(dir1, Internal) and isinstance(dir2, Internal))
    )
