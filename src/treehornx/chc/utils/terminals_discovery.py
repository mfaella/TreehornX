from collections import deque
from dataclasses import dataclass
from typing import Iterable

from treehornx.chc.utils import end_of_lace
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Dir, Down, Up
from treehornx.enum_labels.core.Label import Label


@dataclass(slots=True, frozen=True)
class _DiscoveredAsParent:
    child_key: int | str


@dataclass(slots=True, frozen=True)
class _DiscoveredAsChild:
    pass


@dataclass(slots=True, frozen=True)
class _DiscoveredAsEndOfLace:
    pass


type _DiscoveryKind = _DiscoveredAsParent | _DiscoveredAsChild | _DiscoveredAsEndOfLace


def _get_only_terminals(labels: set[Label]) -> set[Label]:
    origins = set(label.origin for label in labels)
    terminals = labels.difference(origins)
    return terminals


def _discover_terminals_by_direction(
    trees: KnittedTrees, lab: Label, dir: Dir
) -> Iterable[tuple[Label, _DiscoveryKind]]:
    match dir:
        case Up():
            pairs = set(pair for pair in trees.pairs() if pair[1] == lab)
            parents = set(pair[0] for pair in pairs)
            terminal_parents = _get_only_terminals(parents)
            for parent, _, child_key in pairs:
                if parent in terminal_parents:
                    yield parent, _DiscoveredAsParent(child_key)
        case Down(j):
            pairs = set(pair for pair in trees.pairs() if pair[0] == lab and pair[2] == j)
            children = set(pair[1] for pair in pairs)
            terminal_children = _get_only_terminals(children)
            for _, child, child_key in pairs:
                if child in terminal_children:
                    yield child, _DiscoveredAsChild()
        case _:
            raise ValueError(f"Unsupported direction: {dir}")


def _discovery_directions(trees: KnittedTrees, exclude: Dir | None) -> Iterable[Dir]:
    if exclude != Up():
        yield Up()
    for j in trees.child_keys:
        if Down(j) != exclude:
            yield Down(j)


def generate_L_P_Terminal(trees: KnittedTrees) -> tuple[set[Label], set[tuple[Label, Label, int | str]]]:  # noqa: N802
    P_Terminal: set[tuple[Label, Label, int | str]] = set()  # noqa: N806
    visited: set[tuple[Label, _DiscoveryKind]] = set()
    queue: deque[tuple[Label, _DiscoveryKind]] = deque(
        (lab, _DiscoveredAsEndOfLace()) for lab in trees.labels() if end_of_lace(lab)
    )

    while queue:
        lab, discovery_kind = queue.popleft()
        if (lab, discovery_kind) in visited:
            continue
        visited.add((lab, discovery_kind))
        match discovery_kind:
            case _DiscoveredAsEndOfLace():
                excluded_dir = None
            case _DiscoveredAsChild():
                excluded_dir = Up()
            case _DiscoveredAsParent(child_key):
                excluded_dir = Down(child_key)
        for dir in _discovery_directions(trees, excluded_dir):
            for discovered_lab, new_discovery_kind in _discover_terminals_by_direction(trees, lab, dir):
                if dir == Up():
                    assert isinstance(new_discovery_kind, _DiscoveredAsParent)
                    P_Terminal.add((discovered_lab, lab, new_discovery_kind.child_key))
                else:
                    assert isinstance(dir, Down)
                    P_Terminal.add((lab, discovered_lab, dir.child))
                queue.append((discovered_lab, new_discovery_kind))

    L_Terminal: set[Label] = set()  # noqa: N806
    for p in P_Terminal:
        L_Terminal.add(p[0])
        L_Terminal.add(p[1])

    return L_Terminal, P_Terminal
