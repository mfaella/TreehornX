"""The result of a symbolic engine: states, edges and the roots where the queries fire, with the splits by root.

The *body* of a root is the set of states it reaches through the edges, the root excluded. A tree restricted to some
roots keeps those roots, their bodies and the edges whose parent is one of them: the bodies are closed under the
edges, so the CHC system of the restricted tree holds every clause the queries of its roots depend on."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Generic, Iterable, TypeVar

from treehornx.symbolic.Edge import Edge


S = TypeVar("S")
C = TypeVar("C")

NO_SPLIT = 0
SPLIT_BY_PARTIAL_BODY = 1
SPLIT_BY_BODY = 2
SPLIT_BY_ROOT = 3


@dataclass(frozen=True)
class SymbolicTree(Generic[S, C]):
    edges: frozenset[Edge[S, C]]
    roots: frozenset[S]
    """The states where a query fires (`SymbolicEngine.is_root`)."""

    @cached_property
    def states(self) -> frozenset[S]:
        """The roots and the states of the edges."""
        return self.roots | {state for edge in self.edges for state in (edge.parent, edge.child)}

    @cached_property
    def _children(self) -> dict[S, set[S]]:
        children: dict[S, set[S]] = defaultdict(set)
        for edge in self.edges:
            children[edge.parent].add(edge.child)
        return children

    def body(self, root: S) -> frozenset[S]:
        """The states reachable from `root` through the edges, `root` excluded (unless an edge leads back to it)."""
        children = self._children
        seen = set(children.get(root, ()))
        work = list(seen)
        while work:
            for child in children.get(work.pop(), ()):
                if child not in seen:
                    seen.add(child)
                    work.append(child)
        return frozenset(seen)

    def restrict(self, roots: Iterable[S], body: frozenset[S]) -> SymbolicTree[S, C]:
        """The tree of `roots` and `body`: the edges whose parent is one of them."""
        kept_roots = frozenset(roots)
        states = kept_roots | body
        return SymbolicTree(frozenset(e for e in self.edges if e.parent in states), kept_roots)

    def _bodies(self) -> dict[frozenset[S], list[S]]:
        """Body → its roots, in the order of `self.roots`."""
        groups: dict[frozenset[S], list[S]] = {}
        for root in self.roots:
            groups.setdefault(self.body(root), []).append(root)
        return groups

    def split_by_root(self) -> set[SymbolicTree[S, C]]:
        """One tree per root."""
        return {self.restrict([root], self.body(root)) for root in self.roots}

    def split_by_body(self) -> set[SymbolicTree[S, C]]:
        """One tree per set of roots with the same body (the same derivations)."""
        return {self.restrict(roots, body) for body, roots in self._bodies().items()}

    def split_by_partial_body(self) -> set[SymbolicTree[S, C]]:
        """`split_by_body`, then each tree whose body is strictly included in the body of another goes into the
        smallest maximal one including it (fewest body states, then the first root in the order of `self.roots`)."""
        groups = self._bodies()
        index = {root: i for i, root in enumerate(self.roots)}
        bodies = list(groups)
        maximal = [body for body in bodies if not any(body < other for other in bodies)]
        members: dict[frozenset[S], list[S]] = {body: list(groups[body]) for body in maximal}
        for body in bodies:
            if body not in members:
                target = min(
                    (other for other in maximal if body < other),
                    key=lambda other: (len(other), min(index[root] for root in groups[other])),
                )
                members[target].extend(groups[body])
        return {self.restrict(roots, body) for body, roots in members.items()}

    def split(self, level: int) -> set[SymbolicTree[S, C]]:
        """The split of `--split level`: 0 none, 1 by partial body, 2 by body, 3 by root."""
        match level:
            case 0:
                return {self}
            case 1:
                return self.split_by_partial_body()
            case 2:
                return self.split_by_body()
            case 3:
                return self.split_by_root()
            case _:
                raise ValueError(f"unknown split level {level}")


def ordered(trees: Iterable[SymbolicTree[S, C]], whole: SymbolicTree[S, C]) -> list[SymbolicTree[S, C]]:
    """`trees` (parts of `whole`) sorted by the position of their first root in `whole.roots`, so the systems built
    from them come out in a fixed order; trees without roots go last."""
    index = {root: i for i, root in enumerate(whole.roots)}
    return sorted(trees, key=lambda tree: min((index[root] for root in tree.roots), default=len(index)))
