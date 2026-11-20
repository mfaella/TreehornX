from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Generic, TypeVar


S = TypeVar("S")


@dataclass(frozen=True, slots=True)
class Edge(Generic[S]):
    """An edge of a symbolic tree: the state of a parent, the state of its child and the index j of the child
    (0-based, below the arity of the engine)."""

    parent: S
    child: S
    j: int


L = TypeVar("L")
R = TypeVar("R")

NO_SPLIT = 0
SPLIT_BY_PARTIAL_BODY = 1
SPLIT_BY_BODY = 2
SPLIT_BY_ROOT = 3


@dataclass(frozen=True)
class SymbolicTree(Generic[L]):
    edges: frozenset[Edge[L]]
    roots: frozenset[L]
    """The states where a query fires."""
    arity: int
    """The number of children of a node: the child indexes are 0 .. arity-1."""
    leaves: frozenset[L]
    """The states with no children, final when they are reached Disjoint from `roots`."""

    @cached_property
    def labels(self) -> frozenset[L]:
        """The roots, the leaves and the states of the edges."""
        return self.roots | self.leaves | {state for edge in self.edges for state in (edge.parent, edge.child)}

    @cached_property
    def _children(self) -> dict[L, set[L]]:
        children: dict[L, set[L]] = defaultdict(set)
        for edge in self.edges:
            children[edge.parent].add(edge.child)
        return children

    def body(self, root: L) -> frozenset[L]:
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

    def filter_edges(self, keep: Callable[[Edge[L]], bool]) -> SymbolicTree[L]:
        """The edges kept by `keep` that compose a finite tree from a root down to leaves (`leaves`).

        A state is final when it is a leaf or every child index below `arity` has a kept edge to a final child: a
        least fixpoint computed bottom-up from the leaves in linear time, so a cycle counts only when another edge
        of the same slot gives the base case. The result keeps the final roots and the kept edges to final
        children reachable from them, with the leaves among them."""
        kept = [edge for edge in self.edges if keep(edge)]
        by_child: defaultdict[L, list[Edge[L]]] = defaultdict(list)
        for edge in kept:
            by_child[edge.child].append(edge)
        arity = self.arity
        final = set(self.leaves)
        slots: defaultdict[L, set[int]] = defaultdict(set)
        work = deque(final)
        while work:
            child = work.pop()
            for edge in by_child[child]:
                parent = edge.parent
                if parent in final or edge.j in slots[parent]:
                    continue
                slots[parent].add(edge.j)
                if len(slots[parent]) == arity:
                    final.add(parent)
                    work.append(parent)

        roots = frozenset(root for root in self.roots if root in final)
        by_parent: defaultdict[L, list[Edge[L]]] = defaultdict(list)
        for edge in kept:
            if edge.child in final:
                by_parent[edge.parent].append(edge)
        final_edges: set[Edge[L]] = set()
        seen: set[L] = set(roots)
        stack = list(roots)
        while stack:
            for edge in by_parent[stack.pop()]:
                final_edges.add(edge)
                if edge.child not in seen:
                    seen.add(edge.child)
                    stack.append(edge.child)
        return SymbolicTree(frozenset(final_edges), roots, arity, self.leaves & seen)

    def map(self, mapping: Callable[[SymbolicTree[L], L], R]) -> SymbolicTree[R]:
        """The tree with every state replaced by `mapping(self, state)`, computed once per state. `mapping` gets the
        tree too, so the new state can depend on the edges, the roots or the leaves. States mapped to the same new
        state are merged."""
        states = {state: mapping(self, state) for state in self.labels}
        return SymbolicTree(
            frozenset(Edge(states[e.parent], states[e.child], e.j) for e in self.edges),
            frozenset(states[root] for root in self.roots),
            self.arity,
            frozenset(states[leaf] for leaf in self.leaves),
        )

    def restrict(self, roots: Iterable[L], body: frozenset[L]) -> SymbolicTree[L]:
        """The tree of `roots` and `body`: the edges whose parent is one of them, the leaves among them."""
        kept_roots = frozenset(roots)
        states = kept_roots | body
        edges = frozenset(e for e in self.edges if e.parent in states)
        return SymbolicTree(edges, kept_roots, self.arity, self.leaves & states)

    def _bodies(self) -> dict[frozenset[L], list[L]]:
        """Body → its roots, in the order of `self.roots`."""
        groups: dict[frozenset[L], list[L]] = {}
        for root in self.roots:
            groups.setdefault(self.body(root), []).append(root)
        return groups

    def split_by_root(self) -> set[SymbolicTree[L]]:
        """One tree per root."""
        return {self.restrict([root], self.body(root)) for root in self.roots}

    def split_by_body(self) -> set[SymbolicTree[L]]:
        """One tree per set of roots with the same body (the same derivations)."""
        return {self.restrict(roots, body) for body, roots in self._bodies().items()}

    def split_by_partial_body(self) -> set[SymbolicTree[L]]:
        """`split_by_body`, then each tree whose body is strictly included in the body of another goes into the
        smallest maximal one including it (fewest body states, then the first root in the order of `self.roots`)."""
        groups = self._bodies()
        index = {root: i for i, root in enumerate(self.roots)}
        bodies = list(groups)
        maximal = [body for body in bodies if not any(body < other for other in bodies)]
        members: dict[frozenset[L], list[L]] = {body: list(groups[body]) for body in maximal}
        for body in bodies:
            if body not in members:
                target = min(
                    (other for other in maximal if body < other),
                    key=lambda other: (len(other), min(index[root] for root in groups[other])),
                )
                members[target].extend(groups[body])
        return {self.restrict(roots, body) for body, roots in members.items()}

    def split(self, level: int) -> set[SymbolicTree[L]]:
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


def ordered(trees: Iterable[SymbolicTree[L]], whole: SymbolicTree[L]) -> list[SymbolicTree[L]]:
    """`trees` (parts of `whole`) sorted by the position of their first root in `whole.roots`, so the systems built
    from them come out in a fixed order; trees without roots go last."""
    index = {root: i for i, root in enumerate(whole.roots)}
    return sorted(trees, key=lambda tree: min((index[root] for root in tree.roots), default=len(index)))
