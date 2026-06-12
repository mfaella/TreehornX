from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol, Self

from treehornx.chc.utils import end_of_lace
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Dir, Down, Up
from treehornx.enum_labels.core.Label import Label


@dataclass(slots=True, frozen=True)
class Pair[T]:
    parent: T
    child: T
    child_key: int | str

@dataclass(slots=True, frozen=True)
class _DiscoveredAsParent:
    child_key: int | str


@dataclass(slots=True, frozen=True)
class _DiscoveredAsChild:
    pass


@dataclass(slots=True, frozen=True)
class _DiscoveredAsEndOfProcess:
    pass


type _DiscoveryKind = _DiscoveredAsParent | _DiscoveredAsChild | _DiscoveredAsEndOfProcess


def _get_only_terminals[T](items: set[T], get_origin: Callable[[T], T | None]) -> set[T]:
    origins = set(get_origin(item) for item in items)
    terminals = items.difference(origins)
    return terminals


def _discover_terminals_by_direction[T](
    pairs: set[Pair[T]], item: T, dir: Dir, get_origin: Callable[[T], T | None]
) -> Iterable[tuple[T, _DiscoveryKind]]:
    match dir:
        case Up():
            pairs = set(pair for pair in pairs if pair.child == item)
            parents = set(pair.parent for pair in pairs)
            terminal_parents = _get_only_terminals(parents, get_origin)
            for pair in pairs:
                if pair.parent in terminal_parents:
                    yield pair.parent, _DiscoveredAsParent(pair.child_key)
        case Down(j):
            pairs = set(pair for pair in pairs if pair.parent == item and pair.child_key == j)
            children = set(pair.child for pair in pairs)
            terminal_children = _get_only_terminals(children, get_origin)
            for pair in pairs:
                if pair.child in terminal_children:
                    yield pair.child, _DiscoveredAsChild()
        case _:
            raise ValueError(f"Unsupported direction: {dir}")


def _discovery_directions(child_keys: Iterable[str | int], exclude: Dir | None) -> Iterable[Dir]:
    if exclude != Up():
        yield Up()
    for j in child_keys:
        if Down(j) != exclude:
            yield Down(j)


def generate_terminals[T](pairs: set[Pair[T]], end_of_process: Callable[[T], bool], get_origin: Callable[[T], T | None]) -> tuple[set[T], set[Pair[T]]]:  # noqa: N802
    P_Terminal: set[Pair[T]] = set()  # noqa: N806
    items: set[T] = set()
    child_keys: set[int | str] = set()
    for pair in pairs:
        items.add(pair.parent)
        items.add(pair.child)
        child_keys.add(pair.child_key)
    visited: set[tuple[T, _DiscoveryKind]] = set()
    queue: deque[tuple[T, _DiscoveryKind]] = deque(
        (item, _DiscoveredAsEndOfProcess()) for item in items if end_of_process(item)
    )

    while queue:
        item, discovery_kind = queue.popleft()
        if (item, discovery_kind) in visited:
            continue
        visited.add((item, discovery_kind))
        match discovery_kind:
            case _DiscoveredAsEndOfProcess():
                excluded_dir = None
            case _DiscoveredAsChild():
                excluded_dir = Up()
            case _DiscoveredAsParent(child_key):
                excluded_dir = Down(child_key)
        for dir in _discovery_directions(child_keys, excluded_dir):
            for discovered_lab, new_discovery_kind in _discover_terminals_by_direction(pairs, item, dir, get_origin):
                # print("lez go")
                if dir == Up():
                    assert isinstance(new_discovery_kind, _DiscoveredAsParent)
                    P_Terminal.add(Pair(discovered_lab, item, new_discovery_kind.child_key))
                else:
                    assert isinstance(dir, Down)
                    P_Terminal.add(Pair(item, discovered_lab, dir.child))
                queue.append((discovered_lab, new_discovery_kind))

    L_Terminal: set[T] = set()  # noqa: N806
    for p in P_Terminal:
        L_Terminal.add(p.parent)
        L_Terminal.add(p.child)

    return L_Terminal, P_Terminal

def generate_terminals_from_trees(trees: KnittedTrees) -> tuple[set[Label], set[Pair[Label]]]:  # noqa: N802
    pairs = set(map(lambda tup: Pair(*tup), trees.pairs()))
    return generate_terminals(pairs, end_of_lace, lambda lab: lab.origin)
