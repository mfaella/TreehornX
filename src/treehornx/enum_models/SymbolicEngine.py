"""Generic worklist fixpoint over trees of states.

The engine enumerates states S (the information of a node) and edges `Edge[S]` (a parent state, a child state and
the index j of the child) reachable from the edges and the states of the input tree (`tree`) through three kinds of
steps:
internal steps of a state (`step_int`), steps from a child to its parent (`step_up`) and steps from a parent to a
child (`step_down`). When a state steps, the new state is propagated to the edges of the old one, except the edges
the step concerns (`_excluded_child`).

The engine does not intern states or edges: the subclasses build their states through a factory that interns them.
The states and edges on which a step was taken are kept in `steppable`. `finals` keeps the saturated states and
edges (no step was taken on them) that compose a finite tree from a root down to leaves, through
`SymbolicTree.filter_edges`. The roots and the leaves start from those of the input tree (`roots`, `leaves`); a
transition adds its new state to the set of its old state, so a step never makes a root or a leaf out of another
state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from typing import Iterable, Union

from typing_extensions import override

from treehornx.symbolic_tree import Edge, SymbolicTree
from treehornx.enum_models.labels import TLab


@dataclass(frozen=True, slots=True)
class _Up:
    """The child stepped to its parent."""


@dataclass(frozen=True, slots=True)
class _Internal:
    """The state stepped internally."""


@dataclass(frozen=True, slots=True)
class _Down:
    """The parent stepped to its child of index `child`."""

    child: int


_TransitionDirection = Union[_Up, _Internal, _Down]


@dataclass(frozen=True, slots=True)
class Transition:
    label: TLab
    label_new: TLab
    dir: _TransitionDirection


@dataclass
class SymbolicExecutionEngine(ABC):
    tree: SymbolicTree[TLab]
    """The input: the initial edges, states, roots and leaves, and the arity of a node."""

    _fixed: bool = field(default=False, init=False)
    _roots: set[TLab] = field(default_factory=set[TLab], init=False)
    """The states where a query fires: the roots of `tree` and the states a transition reaches from a root."""
    _leaves: set[TLab] = field(default_factory=set[TLab], init=False)
    """The states with no children, final when they are reached: the leaves of `tree` and the states a transition
    reaches from a leaf."""

    _edges: set[Edge[TLab]] = field(default_factory=set[Edge[TLab]], init=False)
    _states: set[TLab] = field(default_factory=set[TLab], init=False)
    _steppable: set[TLab | Edge[TLab]] = field(default_factory=set[TLab | Edge[TLab]], init=False)
    """The states and edges on which a step was taken."""

    _transitions: defaultdict[TLab, set[Transition]] = field(
        default_factory=lambda: defaultdict[TLab, set[Transition]](set), init=False
    )
    _dirty: set[Transition] = field(default_factory=set[Transition], init=False)
    _parent_pending_updates: defaultdict[Transition, deque[Edge[TLab]]] = field(
        default_factory=lambda: defaultdict[Transition, deque[Edge[TLab]]](deque), init=False
    )
    _child_pending_updates: defaultdict[Transition, deque[Edge[TLab]]] = field(
        default_factory=lambda: defaultdict[Transition, deque[Edge[TLab]]](deque), init=False
    )

    _edge_parent_index: defaultdict[TLab, set[Edge[TLab]]] = field(
        default_factory=lambda: defaultdict[TLab, set[Edge[TLab]]](set), init=False
    )
    _edge_child_index: defaultdict[TLab, set[Edge[TLab]]] = field(
        default_factory=lambda: defaultdict[TLab, set[Edge[TLab]]](set), init=False
    )

    def __post_init__(self):
        self._roots.update(self.tree.roots)
        self._leaves.update(self.tree.leaves)
        for edge in self.tree.edges:
            self._add_edge(edge)
        for state in self.tree.labels:
            self._add_state(state)

    @property
    def arity(self) -> int:
        """The number of children of a node: the child indexes are 0 .. arity-1."""
        return self.tree.arity

    @abstractmethod
    def step_up(self, edge: Edge[TLab], /) -> Edge[TLab] | None: ...

    @abstractmethod
    def step_down(self, edge: Edge[TLab], /) -> Edge[TLab] | None: ...

    @abstractmethod
    def step_int(self, state: TLab, /) -> Iterable[TLab] | None: ...

    def _step_up_wrapper(self, edge: Edge[TLab], /) -> Edge[TLab] | None:
        return self.step_up(edge)

    def _step_down_wrapper(self, edge: Edge[TLab], /) -> Edge[TLab] | None:
        return self.step_down(edge)

    def _step_int_wrapper(self, state: TLab, /) -> Iterable[TLab] | None:
        return self.step_int(state)

    @staticmethod
    def _excluded_child(dir: _TransitionDirection) -> int | None:
        """The index of the edges a transition does not propagate to as parent: the child it stepped from."""
        return dir.child if isinstance(dir, _Down) else None

    def _enqueue_parent(self, trans: Transition, edge: Edge[TLab]):
        excluded = self._excluded_child(trans.dir)
        if excluded is None or edge.j != excluded:
            self._parent_pending_updates[trans].append(edge)
            self._dirty.add(trans)

    def _enqueue_child(self, trans: Transition, edge: Edge[TLab]):
        if not isinstance(trans.dir, _Up):
            self._child_pending_updates[trans].append(edge)
            self._dirty.add(trans)

    def _add_transition(self, state: TLab, new_state: TLab, dir: _TransitionDirection):
        transition = Transition(state, new_state, dir)
        if transition in self._transitions[state]:
            return
        self._transitions[state].add(transition)
        if state in self._roots:
            self._roots.add(new_state)
        if state in self._leaves:
            self._leaves.add(new_state)
        for edge in self._edge_parent_index[state]:
            self._enqueue_parent(transition, edge)
        if not isinstance(dir, _Up):
            for edge in self._edge_child_index[state]:
                self._enqueue_child(transition, edge)

    def _add_edge(self, edge: Edge[TLab]):
        if edge in self._edges:
            return
        self._edges.add(edge)
        # register the states of the edge, as the old interning did (without propagating their transitions)
        self._states.add(edge.parent)
        self._states.add(edge.child)
        self._edge_parent_index[edge.parent].add(edge)
        self._edge_child_index[edge.child].add(edge)
        for trans in self._transitions[edge.parent]:
            self._enqueue_parent(trans, edge)
        for trans in self._transitions[edge.child]:
            self._enqueue_child(trans, edge)

    def _add_state(self, state: TLab):
        if state in self._states:
            return
        self._states.add(state)
        for trans in self._transitions[state]:
            for edge in self._edge_parent_index[state]:
                self._enqueue_parent(trans, edge)
            if not isinstance(trans.dir, _Up):
                for edge in self._edge_child_index[state]:
                    self._enqueue_child(trans, edge)

    def _find_new_edges(self) -> Iterable[Edge[TLab]]:
        new_edges: set[Edge[TLab]] = set()
        dirty, self._dirty = self._dirty, set()
        for trans in dirty:
            queue = self._parent_pending_updates.pop(trans, deque())
            while queue:
                new_edges.add(replace(queue.popleft(), parent=trans.label_new))

            queue = self._child_pending_updates.pop(trans, deque())
            while queue:
                new_edges.add(replace(queue.popleft(), child=trans.label_new))

        for edge in new_edges:
            self._add_edge(edge)

        return iter(e for e in new_edges)

    def _fix(self):
        if self._fixed:
            return
        # the initial states are built outside the engine: register them before anything refers to them
        for edge in self.tree.edges:
            self._add_edge(edge)

        qe: deque[Edge[TLab]] = deque(self.tree.edges)
        qs: deque[TLab] = deque(self.tree.labels)

        visited: set[TLab | Edge[TLab]] = set()

        def qsappend(state: TLab):
            if state not in visited:
                self._add_state(state)
                qs.append(state)
                visited.add(state)

        def qeappend(edge: Edge[TLab]):
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
                    self._steppable.add(state)
                    qsappend(new_state)
                    self._add_transition(state, new_state, _Internal())

            while qe:
                edge = qe.popleft()

                new_edge = self.step_up(edge)
                if new_edge:
                    self._steppable.add(edge)
                    qsappend(new_edge.parent)
                    qeappend(new_edge)
                    self._add_transition(edge.parent, new_edge.parent, _Down(new_edge.j))
                    continue  # might be removed

                new_edge = self.step_down(edge)
                if new_edge:
                    self._steppable.add(edge)
                    qsappend(new_edge.child)
                    qeappend(new_edge)
                    self._add_transition(edge.child, new_edge.child, _Up())

            for edge in self._find_new_edges():
                qsappend(edge.parent)
                qsappend(edge.child)
                qeappend(edge)

        self._fixed = True

    def _is_saturated(self, e: Edge[TLab]) -> bool:
        """Whether no step was taken on the edge `e` and its two states."""
        return len(self._steppable.intersection({e, e.parent, e.child})) == 0

    def finals(self) -> SymbolicTree[TLab]:
        """The saturated states and edges that compose a finite tree from a root down to leaves
        (`SymbolicTree.filter_edges` with `_is_saturated`)."""
        return self.whole().filter_edges(self._is_saturated)

    def whole(self) -> SymbolicTree[TLab]:
        self._fix()
        """Every state and edge reached, with the roots and the leaves."""
        return SymbolicTree(frozenset(self._edges), frozenset(self._roots), self.arity, frozenset(self._leaves))
