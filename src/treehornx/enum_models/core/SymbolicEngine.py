


from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Iterable


from treehornx.enum_models.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_models.core.Label import Label, make_label
from treehornx.enum_models.core.Pair import Pair

@dataclass(frozen=True, slots=True)
class Transition[F]:
    label: Label[F]
    label_new: Label[F]
    dir: Dir

def replace_next[F](label: Label[F], new_next: tuple[Dir, int] | None) -> Label[F]:
    return make_label(label.frame, next=new_next, prev=label.prev, prefix=label.prefix)

@dataclass
class SymbolicEngine[F](ABC):
    k: int
    m: int
    n: int
    initial_pairs: set[Pair[F]]
    start_labels: set[Label[F]]
    pairs: set[Pair[F]] = field(default_factory=set, init=False)
    labels: set[Label[F]] = field(default_factory=set, init=False)

    transitions: dict[Label[F], set[Transition[F]]] = field(default_factory=lambda: defaultdict(set), init=False)
    visited: defaultdict[Transition[F], set[Pair[F]]] = field(default_factory=lambda: defaultdict(set), init=False)
    parent_pending_updates: defaultdict[Transition[F], deque[Pair[F]]] = field(default_factory=lambda: defaultdict(deque), init=False)
    child_pending_updates: defaultdict[Transition[F], deque[Pair[F]]] = field(default_factory=lambda: defaultdict(deque), init=False)

    pair_parent_index: defaultdict[Label[F], set[Pair[F]]] = field(default_factory=lambda: defaultdict(set), init=False)
    pair_child_index: defaultdict[Label[F], set[Pair[F]]] = field(default_factory=lambda: defaultdict(set), init=False)


    @abstractmethod
    def step_up(self, pair: Pair[F], expected_next_dir: Dir) -> F | None:
        ...

    @abstractmethod
    def step_down(self, pair: Pair[F], expected_next_dir: Dir) -> F | None:
        ...

    @abstractmethod
    def step_int(self, label: Label[F], expected_next_dir: Dir) -> Iterable[F] | None:
        ...

    @abstractmethod
    def is_continuos(self, label: Label[F]) -> bool:
        ...

    @abstractmethod
    def is_end_of_lace(self, label: Label[F]) -> bool:
        ...

    def add_transition(self, label: Label[F], new_label: Label[F], dir: Dir):
        transition = Transition(label, new_label, dir)
        if transition in self.transitions[transition.label]:
            return
        self.transitions[label].add(transition)
        excluded_child = self.k+self.m if isinstance(dir, (Up, Internal)) else dir.child
        for pair in self.pair_parent_index[label]:
            if pair.j != excluded_child:
                self.parent_pending_updates[transition].append(pair)

        if not isinstance(dir, Up):
            for pair in self.pair_child_index[label]:
                self.child_pending_updates[transition].append(pair)

    def add_pair(self, pair: Pair[F]):
        if pair in self.pairs:
            return
        self.pairs.add(pair)
        self.labels.add(pair.parent)
        self.labels.add(pair.child)
        self.pair_parent_index[pair.parent].add(pair)
        self.pair_child_index[pair.child].add(pair)
        for trans in self.transitions[pair.parent]:
            self.parent_pending_updates[trans].append(pair)
        for trans in self.transitions[pair.child]:
            self.child_pending_updates[trans].append(pair)

    def psi_up(self, pair: Pair[F]) -> Pair[F] | None:
        if not self.is_continuos(pair.child):
            return

        f = self.step_up(pair, Up())
        if f is None:
            return

        new_parent = make_label(f, next=None, prev=(Down(pair.j), len(pair.child)), prefix=pair.parent)
        new_child = replace_next(pair.child, (Up(), len(new_parent)))

        self.add_transition(pair.parent, new_parent, Down(pair.j))
        self.add_transition(pair.child, new_child, Up())
        new_pair = Pair(new_parent, new_child, pair.j)
        self.add_pair(new_pair)
        return new_pair

    def psi_down(self, pair: Pair[F]) -> Pair[F] | None:
        if not self.is_continuos(pair.parent):
            return

        f = self.step_down(pair, Down(pair.j))
        if f is None:
            return

        new_child = make_label(f, next=None, prev=(Up(), len(pair.parent)), prefix=pair.child)
        new_parent = replace_next(pair.parent, (Down(pair.j), len(new_child)))

        self.add_transition(pair.parent, new_parent, Down(pair.j))
        self.add_transition(pair.child, new_child, Up())
        new_pair = Pair(new_parent, new_child, pair.j)
        self.add_pair(new_pair)
        return new_pair

    def psi_internal(self, label: Label[F]) -> Iterable[Label[F]] | None:
        if not self.is_continuos(label):
            return
        fs = self.step_int(label, Internal())
        if fs is None:
            return

        for f in fs:

            label_wn = replace_next(label, (Internal(), len(label) + 1))
            label_ext = make_label(f, prev=(Internal(), len(label)), next=None, prefix=label_wn)
            self.add_transition(label, label_ext, Internal())
            yield label_ext

    def find_new_pairs(self) -> Iterable[Pair[F]]:
        tmp_pairs: set[Pair[F]] = set()
        for trans in self.parent_pending_updates.keys():
            while self.parent_pending_updates[trans]:
                pair = self.parent_pending_updates[trans].popleft()
                if trans.dir != Down(pair.j):
                    new_pair = replace(pair, parent=trans.label_new)
                    tmp_pairs.add(new_pair)
                self.visited[trans].add(pair)


        for trans in self.child_pending_updates.keys():
            if trans.dir != Up():
                while self.child_pending_updates[trans]:
                    pair = self.child_pending_updates[trans].popleft()
                    new_pair = replace(pair, child=trans.label_new)
                    tmp_pairs.add(new_pair)
                    self.visited[trans].add(pair)

        for pair in tmp_pairs:
            self.add_pair(pair)

        return iter(tmp_pairs)

    def fix(self):
        for pair in self.initial_pairs:
            self.add_pair(pair)

        qp: deque[Pair[F]] = deque(self.initial_pairs)
        ql: deque[Label[F]] = deque(self.start_labels)

        visited: set[Label[F] | Pair[F]] = set()

        def qlappend(label: Label[F]):
            if label not in visited:
                ql.append(label)

        def qpappend(pair: Pair[F]):
            if pair not in visited:
                qp.append(pair)

        while (qp or ql):
            while ql:
                label = ql.popleft()
                visited.add(label)

                labels_ext = self.psi_internal(label)
                if labels_ext:
                    for label_ext in labels_ext:
                        qlappend(label_ext)

            while qp:
                pair = qp.popleft()
                visited.add(pair)

                pair_ext = self.psi_up(pair)
                if pair_ext:
                    qlappend(pair_ext.parent)
                    qlappend(pair_ext.child)
                    qpappend(pair_ext)
                    continue

                pair_ext = self.psi_down(pair)
                if pair_ext:
                    qlappend(pair_ext.parent)
                    qlappend(pair_ext.child)
                    qpappend(pair_ext)
                    continue



            for pair in self.find_new_pairs():
                qlappend(pair.parent)
                qlappend(pair.child)
                qpappend(pair)

    def finals(self) -> tuple[set[Label[F]], set[Pair[F]]]:
        q: deque[tuple[Label[F], Dir]] = deque((lab, Internal()) for lab in self.labels if self.is_end_of_lace(lab))
        visited: set[tuple[Label[F], Dir]] = set()
        final_labels: set[Label[F]] = set()
        final_pairs: set[Pair[F]] = set()

        while q:
            label, dir = q.popleft()
            if (label, dir) in visited:
                continue
            visited.add((label, dir))
            final_labels.add(label)

            excluded_child = self.k + self.m if isinstance(dir, (Up, Internal)) else dir.child
            for pair in self.pair_parent_index[label]:
                if pair.j != excluded_child:
                    final_pairs.add(pair)
                    q.append((pair.child, Up()))

            if not isinstance(dir, Up):
                for pair in self.pair_child_index[label]:
                    final_pairs.add(pair)
                    q.append((pair.parent, Down(pair.j)))

        return final_labels, final_pairs
