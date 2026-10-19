


from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import chain, count
from typing import Iterable


from treehornx.enum_models.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_models.core.InternedPool import InternedPool, InternedPoolView
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair

@dataclass(frozen=True, slots=True)
class Transition[SN]:
    label: SN
    label_new: SN
    dir: Dir

@dataclass
class SymbolicEngine[SN](ABC):
    k: int
    m: int
    initial_pairs: set[Pair[SN]]
    start_states: set[SN]
    pairs: InternedPool[Pair[SN]] = field(default_factory=InternedPool, init=False)
    states: InternedPool[SN] = field(default_factory=InternedPool, init=False)

    transitions: dict[SN, set[Transition[SN]]] = field(default_factory=lambda: defaultdict(set), init=False)
    dirty: set[Transition[SN]] = field(default_factory=set, init=False)
    parent_pending_updates: defaultdict[Transition[SN], deque[Pair[SN]]] = field(default_factory=lambda: defaultdict(deque), init=False)
    child_pending_updates: defaultdict[Transition[SN], deque[Pair[SN]]] = field(default_factory=lambda: defaultdict(deque), init=False)

    pair_parent_index: defaultdict[SN, set[Pair[SN]]] = field(default_factory=lambda: defaultdict(set), init=False)
    pair_child_index: defaultdict[SN, set[Pair[SN]]] = field(default_factory=lambda: defaultdict(set), init=False)

    def __post_init__(self):
        for pair in self.initial_pairs:
            if not self.consistent(pair):
                raise ValueError(f"Initial pair {pair} is not consistent")
            self.add_pair(pair)
        for state in self.start_states:
            self.add_state(state)

    @abstractmethod
    def step_up(self, pair: Pair[SN]) -> Pair[SN] | None:
        ...

    @abstractmethod
    def step_down(self, pair: Pair[SN]) -> Pair[SN] | None:
        ...

    @abstractmethod
    def step_int(self, label: SN) -> Iterable[SN] | None:
        ...

    @abstractmethod
    def consistent(self, pair: Pair[SN]) -> bool:
        ...

    def _excluded_child(self, dir: Dir) -> int:
        excluded_child = self.k+self.m if isinstance(dir, (Up, Internal)) else dir.child
        return excluded_child

    def _enqueue_parent(self, trans: Transition[SN], pair: Pair[SN]):
        if pair.j != self._excluded_child(trans.dir):
            self.parent_pending_updates[trans].append(pair)
            self.dirty.add(trans)

    def _enqueue_child(self, trans: Transition[SN], pair: Pair[SN]):
        if not isinstance(trans.dir, Up):
            self.child_pending_updates[trans].append(pair)
            self.dirty.add(trans)

    def add_transition(self, node_state: SN, new_node_state: SN, dir: Dir):
        transition = Transition(node_state, new_node_state, dir)
        if transition in self.transitions[transition.label]:
            return
        self.transitions[node_state].add(transition)
        for pair in self.pair_parent_index[node_state]:
            self._enqueue_parent(transition, pair)

        if transition.dir != Up():
            for pair in self.pair_child_index[node_state]:
                self._enqueue_child(transition, pair)

    def add_pair(self, pair: Pair[SN]):
        if pair in self.pairs:
            return
        if not self.consistent(pair):
            return
        parent = self.states.intern(pair.parent)
        child = self.states.intern(pair.child)
        pair = self.pairs.intern(replace(pair, parent=parent, child=child))

        self.pair_parent_index[pair.parent].add(pair)
        self.pair_child_index[pair.child].add(pair)
        for trans in self.transitions[pair.parent]:
            self._enqueue_parent(trans, pair)
        for trans in self.transitions[pair.child]:
            self._enqueue_child(trans, pair)

    def add_state(self, node_state: SN):
        if node_state in self.states:
            return
        node_state = self.states.intern(node_state)
        for trans in self.transitions[node_state]:
            for pair in self.pair_parent_index[node_state]:
                self._enqueue_parent(trans, pair)
            if trans.dir != Up():
                for pair in self.pair_child_index[node_state]:
                    self._enqueue_child(trans, pair)

    def consume_internal_steps(self, node_state: SN) -> Iterable[SN] | None:
        node_states = self.step_int(node_state)
        if node_states is None:
            return None
        else:
            return chain.from_iterable(self.consume_internal_steps_rec(ns) for ns in node_states)

    def consume_internal_steps_rec(self, node_state: SN) -> Iterable[SN]:
        node_states = self.step_int(node_state)
        if node_states is None:
            yield node_state
        else:
            for ns in node_states:
                yield from self.consume_internal_steps_rec(ns)

    def find_new_pairs(self) -> Iterable[Pair[SN]]:
        tmp_pairs: set[Pair[SN]] = set()
        dirty, self.dirty = self.dirty, set()
        for trans in dirty:
            pair_queue = self.parent_pending_updates.pop(trans, deque())
            while pair_queue:
                pair = pair_queue.popleft()
                new_pair = replace(pair, parent=trans.label_new)
                tmp_pairs.add(new_pair)

            pair_queue = self.child_pending_updates.pop(trans, deque())
            while pair_queue:
                pair = pair_queue.popleft()
                new_pair = replace(pair, child=trans.label_new)
                tmp_pairs.add(new_pair)

        for pair in tmp_pairs:
            self.add_pair(pair)

        return iter(p for p in tmp_pairs if self.consistent(p))

    def fix(self):
        # the initial labels are built outside the engine: register them before anything refers to them
        for pair in self.initial_pairs:
            self.add_pair(pair)

        qp: deque[Pair[SN]] = deque(self.initial_pairs)
        qs: deque[SN] = deque(self.start_states)

        visited: set[SN | Pair[SN]] = set()

        def qsappend(ns: SN):
            if ns not in visited:
                self.add_state(ns)
                qs.append(ns)
                visited.add(ns)

        def qpappend(pair: Pair[SN]):
            if pair not in visited and self.consistent(pair):
                self.add_pair(pair)
                qp.append(pair)
                visited.add(pair)

        while (qp or qs):
            while qs:
                state = qs.popleft()

                new_states = self.consume_internal_steps(state)
                if new_states:
                    for new_state in new_states:
                        qsappend(new_state)
                        self.add_state(new_state)
                        self.add_transition(state, new_state, Internal())
                else:
                    continue

            while qp:
                pair = qp.popleft()

                new_pair = self.step_up(pair)
                if new_pair:
                    qsappend(new_pair.parent)
                    qpappend(new_pair)
                    self.add_transition(pair.parent, new_pair.parent, Down(new_pair.j))
                    continue

                new_pair = self.step_down(pair)
                if new_pair:
                    qsappend(new_pair.child)
                    qpappend(new_pair)
                    self.add_transition(pair.child, new_pair.child, Up())
                    continue

            for pair in self.find_new_pairs():
                qsappend(pair.parent)
                qsappend(pair.child)
                qpappend(pair)

    @abstractmethod
    def is_end_of_computation(self, state: SN) -> bool:
        ...

    def finals(self) -> tuple[set[SN], set[Pair[SN]]]:
        q: deque[tuple[SN, Dir]] = deque((ns, Internal()) for ns in iter(self.states) if self.is_end_of_computation(ns))
        visited: set[tuple[SN, Dir]] = set()
        final_states: set[SN] = set()
        final_pairs: set[Pair[SN]] = set()

        while q:
            ns, dir = q.popleft()
            if (ns, dir) in visited:
                continue
            visited.add((ns, dir))
            final_states.add(ns)

            excluded_child = self.k + self.m if isinstance(dir, (Up, Internal)) else dir.child
            for pair in self.pair_parent_index[ns]:
                if pair.j != excluded_child:
                    final_pairs.add(pair)
                    q.append((pair.child, Up()))

            if not isinstance(dir, Up):
                for pair in self.pair_child_index[ns]:
                    final_pairs.add(pair)
                    q.append((pair.parent, Down(pair.j)))

        return final_states, final_pairs

    def clear(self):
        self.transitions.clear()
        self.dirty.clear()
        self.parent_pending_updates.clear()
        self.child_pending_updates.clear()
        self.pair_parent_index.clear()
        self.pair_child_index.clear()
        self.pairs.clear()
        self.states.clear()

    def states_pool(self) -> InternedPoolView[SN]:
        return InternedPoolView(self.states)

    def pairs_pool(self) -> InternedPoolView[Pair[SN]]:
        return InternedPoolView(self.pairs)

    def state_id(self, state: SN) -> int:
        return self.states.get_id(state)

    def pair_id(self, pair: Pair[SN]) -> int:
        return self.pairs.get_id(pair)
