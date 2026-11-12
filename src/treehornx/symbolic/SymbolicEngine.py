"""Generic worklist fixpoint over trees of states.

The engine enumerates states S (the information of a node) and edges `Edge[S, C]` (a parent state, a child state and
the index C of the child) reachable from the initial edges and the start states through three kinds of steps:
internal steps of a state (`step_int`), steps from a child to its parent (`step_up`) and steps from a parent to a
child (`step_down`). When a state steps, the new state is propagated to the edges of the old one, except the edges
the step concerns (`_excluded_child`).

The engine does not intern states or edges: the subclasses build their states through a factory that interns them.
The states and edges on which a step was taken are kept in `steppable`. `finals` keeps the saturated states and
edges (no step was taken on them) that compose a finite tree from a root (`is_root`) down to leaves (`is_leaf`): a
least fixpoint computed bottom-up from the leaves, so a cycle counts only when another edge of the same slot gives
the base case.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from typing import Generic, Iterable, TypeVar, Union

from treehornx.symbolic.Edge import Edge
from treehornx.symbolic.SymbolicTree import SymbolicTree


S = TypeVar("S")
C = TypeVar("C")


@dataclass(frozen=True, slots=True)
class _Up:
    """The child stepped to its parent."""


@dataclass(frozen=True, slots=True)
class _Internal:
    """The state stepped internally."""


@dataclass(frozen=True, slots=True)
class _Down(Generic[C]):
    """The parent stepped to its child of index `child`."""

    child: C


_TransitionDirection = Union[_Up, _Internal, _Down[C]]


@dataclass(frozen=True, slots=True)
class Transition(Generic[S, C]):
    label: S
    label_new: S
    dir: _TransitionDirection[C]


@dataclass
class SymbolicEngine(ABC, Generic[S, C]):
    initial_edges: set[Edge[S, C]]
    start_states: set[S]
    child_indexes: set[C]

    edges: set[Edge[S, C]] = field(default_factory=set[Edge[S, C]], init=False)
    states: set[S] = field(default_factory=set[S], init=False)
    steppable: set[S | Edge[S, C]] = field(default_factory=set[S | Edge[S, C]], init=False)
    """The states and edges on which a step was taken."""

    transitions: defaultdict[S, set[Transition[S, C]]] = field(
        default_factory=lambda: defaultdict[S, set[Transition[S, C]]](set), init=False
    )
    dirty: set[Transition[S, C]] = field(default_factory=set[Transition[S, C]], init=False)
    parent_pending_updates: defaultdict[Transition[S, C], deque[Edge[S, C]]] = field(
        default_factory=lambda: defaultdict[Transition[S, C], deque[Edge[S, C]]](deque), init=False
    )
    child_pending_updates: defaultdict[Transition[S, C], deque[Edge[S, C]]] = field(
        default_factory=lambda: defaultdict[Transition[S, C], deque[Edge[S, C]]](deque), init=False
    )

    edge_parent_index: defaultdict[S, set[Edge[S, C]]] = field(
        default_factory=lambda: defaultdict[S, set[Edge[S, C]]](set), init=False
    )
    edge_child_index: defaultdict[S, set[Edge[S, C]]] = field(
        default_factory=lambda: defaultdict[S, set[Edge[S, C]]](set), init=False
    )

    def __post_init__(self):
        for edge in self.initial_edges:
            self._add_edge(edge)
        for state in self.start_states:
            self._add_state(state)

    @abstractmethod
    def step_up(self, edge: Edge[S, C], /) -> Edge[S, C] | None: ...

    @abstractmethod
    def step_down(self, edge: Edge[S, C], /) -> Edge[S, C] | None: ...

    @abstractmethod
    def step_int(self, state: S, /) -> Iterable[S] | None: ...

    @abstractmethod
    def is_leaf(self, s: S, /) -> bool:
        """Whether `s` is a leaf: it has no children and is final when it is reached. Disjoint from `is_root`."""

    @abstractmethod
    def is_root(self, s: S, /) -> bool:
        """Whether `s` is the root of a tree, where the queries fire. Disjoint from `is_leaf`."""

    def is_edge_saturated(self, e: Edge[S, C], /) -> bool:
        """An extra condition for an edge to be final, on top of no step taken on it or its states (True by
        default)."""
        return True

    @staticmethod
    def _excluded_child(dir: _TransitionDirection[C]) -> C | None:
        """The index of the edges a transition does not propagate to as parent: the child it stepped from."""
        return dir.child if isinstance(dir, _Down) else None

    def _enqueue_parent(self, trans: Transition[S, C], edge: Edge[S, C]):
        excluded = self._excluded_child(trans.dir)
        if excluded is None or edge.j != excluded:
            self.parent_pending_updates[trans].append(edge)
            self.dirty.add(trans)

    def _enqueue_child(self, trans: Transition[S, C], edge: Edge[S, C]):
        if not isinstance(trans.dir, _Up):
            self.child_pending_updates[trans].append(edge)
            self.dirty.add(trans)

    def _add_transition(self, state: S, new_state: S, dir: _TransitionDirection[C]):
        transition = Transition(state, new_state, dir)
        if transition in self.transitions[state]:
            return
        self.transitions[state].add(transition)
        for edge in self.edge_parent_index[state]:
            self._enqueue_parent(transition, edge)
        if not isinstance(dir, _Up):
            for edge in self.edge_child_index[state]:
                self._enqueue_child(transition, edge)

    def _add_edge(self, edge: Edge[S, C]):
        if edge in self.edges:
            return
        self.edges.add(edge)
        # register the states of the edge, as the old interning did (without propagating their transitions)
        self.states.add(edge.parent)
        self.states.add(edge.child)
        self.edge_parent_index[edge.parent].add(edge)
        self.edge_child_index[edge.child].add(edge)
        for trans in self.transitions[edge.parent]:
            self._enqueue_parent(trans, edge)
        for trans in self.transitions[edge.child]:
            self._enqueue_child(trans, edge)

    def _add_state(self, state: S):
        if state in self.states:
            return
        self.states.add(state)
        for trans in self.transitions[state]:
            for edge in self.edge_parent_index[state]:
                self._enqueue_parent(trans, edge)
            if not isinstance(trans.dir, _Up):
                for edge in self.edge_child_index[state]:
                    self._enqueue_child(trans, edge)

    def _find_new_edges(self) -> Iterable[Edge[S, C]]:
        new_edges: set[Edge[S, C]] = set()
        dirty, self.dirty = self.dirty, set()
        for trans in dirty:
            queue = self.parent_pending_updates.pop(trans, deque())
            while queue:
                new_edges.add(replace(queue.popleft(), parent=trans.label_new))

            queue = self.child_pending_updates.pop(trans, deque())
            while queue:
                new_edges.add(replace(queue.popleft(), child=trans.label_new))

        for edge in new_edges:
            self._add_edge(edge)

        return iter(e for e in new_edges)

    def fix(self):
        # the initial states are built outside the engine: register them before anything refers to them
        for edge in self.initial_edges:
            self._add_edge(edge)

        qe: deque[Edge[S, C]] = deque(self.initial_edges)
        qs: deque[S] = deque(self.start_states)

        visited: set[S | Edge[S, C]] = set()

        def qsappend(state: S):
            if state not in visited:
                self._add_state(state)
                qs.append(state)
                visited.add(state)

        def qeappend(edge: Edge[S, C]):
            if edge not in visited:
                self._add_edge(edge)
                qe.append(edge)
                visited.add(edge)

        while qe or qs:
            while qs:
                state = qs.popleft()
                new_states = self.step_int(state)
                if new_states is None:
                    continue
                for new_state in new_states:
                    self.steppable.add(state)
                    qsappend(new_state)
                    self._add_transition(state, new_state, _Internal())

            while qe:
                edge = qe.popleft()

                new_edge = self.step_up(edge)
                if new_edge:
                    self.steppable.add(edge)
                    qsappend(new_edge.parent)
                    qeappend(new_edge)
                    self._add_transition(edge.parent, new_edge.parent, _Down(new_edge.j))
                    continue

                new_edge = self.step_down(edge)
                if new_edge:
                    self.steppable.add(edge)
                    qsappend(new_edge.child)
                    qeappend(new_edge)
                    self._add_transition(edge.child, new_edge.child, _Up())
                    continue

            for edge in self._find_new_edges():
                qsappend(edge.parent)
                qsappend(edge.child)
                qeappend(edge)

    def _is_saturated(self, e: Edge[S, C]) -> bool:
        """Whether no step was taken on the edge `e` and its two states, and `is_edge_saturated` holds."""
        return len(self.steppable.intersection({e, e.parent, e.child})) == 0 and self.is_edge_saturated(e)

    def _final_states(self, saturated: set[Edge[S, C]]) -> set[S]:
        """The least fixpoint, bottom-up from the leaves: a state is final when it is a leaf or every index in
        `child_indexes` has an edge of `saturated` to a final child. Each state enters the worklist once and each
        edge is read once per pop of its child, so the time is linear."""
        by_child: defaultdict[S, list[Edge[S, C]]] = defaultdict(list)
        for edge in saturated:
            by_child[edge.child].append(edge)
        arity = len(self.child_indexes)
        final = {state for state in self.states if self.is_leaf(state)}
        slots: defaultdict[S, set[C]] = defaultdict(set)
        work = list(final)
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
        return final

    def finals(self) -> SymbolicTree[S, C]:
        """The saturated states and edges that compose a finite tree from a root down to leaves: an internal node is
        final when every index in `child_indexes` has a saturated edge to a final child (`_final_states`). The edges
        are those reachable from the final roots through saturated edges to final children."""
        saturated = {edge for edge in self.edges if self._is_saturated(edge)}
        final = self._final_states(saturated)
        roots = frozenset(state for state in self.states if self.is_root(state) and state in final)

        by_parent: defaultdict[S, list[Edge[S, C]]] = defaultdict(list)
        for edge in saturated:
            if edge.child in final:
                by_parent[edge.parent].append(edge)
        final_edges: set[Edge[S, C]] = set()
        seen: set[S] = set(roots)
        stack = list(roots)
        while stack:
            for edge in by_parent[stack.pop()]:
                final_edges.add(edge)
                if edge.child not in seen:
                    seen.add(edge.child)
                    stack.append(edge.child)

        return SymbolicTree(frozenset(final_edges), roots)

    def clear(self):
        self.transitions.clear()
        self.dirty.clear()
        self.parent_pending_updates.clear()
        self.child_pending_updates.clear()
        self.edge_parent_index.clear()
        self.edge_child_index.clear()
        self.edges.clear()
        self.states.clear()
        self.steppable.clear()
