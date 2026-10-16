


from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Iterable


from treehornx.enum_models.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair

@dataclass(frozen=True, slots=True)
class Transition[F]:
    label: Label[F]
    label_new: Label[F]
    dir: Dir


@dataclass
class SymbolicEngine[F](ABC):
    k: int
    m: int
    n: int
    initial_pairs: set[Pair[F]]
    start_labels: set[Label[F]]
    pairs: set[Pair[F]] = field(default_factory=set, init=False)
    labels: dict[Label[F], Label[F]] = field(default_factory=dict, init=False)

    transitions: dict[Label[F], set[Transition[F]]] = field(default_factory=lambda: defaultdict(set), init=False)
    dirty: set[Transition[F]] = field(default_factory=set, init=False)
    parent_pending_updates: defaultdict[Transition[F], deque[Pair[F]]] = field(default_factory=lambda: defaultdict(deque), init=False)
    child_pending_updates: defaultdict[Transition[F], deque[Pair[F]]] = field(default_factory=lambda: defaultdict(deque), init=False)

    pair_parent_index: defaultdict[Label[F], set[Pair[F]]] = field(default_factory=lambda: defaultdict(set), init=False)
    pair_child_index: defaultdict[Label[F], set[Pair[F]]] = field(default_factory=lambda: defaultdict(set), init=False)
    _canonical: dict[Label[F], Label[F]] = field(default_factory=dict, init=False)

    def canonical(self, label: Label[F]) -> Label[F]:
        """The unique object equal to `label`, with its id and a prefix chain made of canonical labels."""
        found = self._canonical.get(label)
        if found is not None:
            return found
        prefix = None if label.prefix is None else self.canonical(label.prefix)
        if prefix is not label.prefix or label._id >= 0:
            # rebuild on a canonical prefix, or copy a label numbered by another engine
            label = Label(label.frame, label.next, label.prev, prefix)
        object.__setattr__(label, "_id", len(self._canonical))
        self._canonical[label] = label
        return label

    def canonical_pair(self, pair: Pair[F]) -> Pair[F]:
        return Pair(self.canonical(pair.parent), self.canonical(pair.child), pair.j)

    def add_label(self, label: Label[F]) -> Label[F]:
        label = self.canonical(label)
        self.labels.setdefault(label, label)
        return label

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

    def _excluded_child(self, dir: Dir) -> int:
        excluded_child = self.k+self.m if isinstance(dir, (Up, Internal)) else dir.child
        return excluded_child

    def _enqueue_parent(self, trans: Transition[F], pair: Pair[F]):
        if pair.j != self._excluded_child(trans.dir):
            self.parent_pending_updates[trans].append(pair)
            self.dirty.add(trans)

    def _enqueue_child(self, trans: Transition[F], pair: Pair[F]):
        if not isinstance(trans.dir, Up):
            self.child_pending_updates[trans].append(pair)
            self.dirty.add(trans)


    def add_transition(self, label: Label[F], new_label: Label[F], dir: Dir):
        transition = Transition(label, new_label, dir)
        if transition in self.transitions[transition.label]:
            return
        self.transitions[label].add(transition)
        for pair in self.pair_parent_index[label]:
            self._enqueue_parent(transition, pair)

        if transition.dir != Up():
            for pair in self.pair_child_index[label]:
                self._enqueue_child(transition, pair)

    def add_pair(self, pair: Pair[F]):
        if pair in self.pairs:
            return
        self.pairs.add(pair)
        self.add_label(pair.parent)
        self.add_label(pair.child)
        self.pair_parent_index[pair.parent].add(pair)
        self.pair_child_index[pair.child].add(pair)
        for trans in self.transitions[pair.parent]:
            self._enqueue_parent(trans, pair)
        for trans in self.transitions[pair.child]:
            self._enqueue_child(trans, pair)

    def psi_up(self, pair: Pair[F]) -> Pair[F] | None:
        if not self.is_continuos(pair.child):
            return

        f = self.step_up(pair, Up())
        if f is None:
            return

        new_parent = self.add_label(Label(f, next=None, prev=(Down(pair.j), len(pair.child)), prefix=pair.parent))
        new_child = self.add_label(replace(pair.child, next=(Up(), len(new_parent))))

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

        new_child = self.add_label(Label(f, next=None, prev=(Up(), len(pair.parent)), prefix=pair.child))
        new_parent = self.add_label(replace(pair.parent, next=(Down(pair.j), len(new_child))))

        self.add_transition(pair.parent, new_parent, Down(pair.j))
        self.add_transition(pair.child, new_child, Up())
        new_pair = Pair(new_parent, new_child, pair.j)
        self.add_pair(new_pair)
        return new_pair

    def consume_internal_steps(self, label: Label[F]) -> Iterable[Label[F]] | None:
        if not self.is_continuos(label):
            return

        fs = self.step_int(label, Internal())
        if fs:
            for f in fs:
                label_wn = self.canonical(replace(label, next=(Internal(), len(label) + 1)))
                label_ext = self.canonical(Label(f, prev=(Internal(), len(label)), next=None, prefix=label_wn))
                yield from self.consume_internal_steps_rec(label_ext)
        else:
            return None

    def consume_internal_steps_rec(self, label: Label[F]) -> Iterable[Label[F]]:
        if not self.is_continuos(label):
            yield label
            return

        fs = self.step_int(label, Internal())
        if fs:
            for f in fs:
                label_wn = self.canonical(replace(label, next=(Internal(), len(label) + 1)))
                label_ext = self.canonical(Label(f, prev=(Internal(), len(label)), next=None, prefix=label_wn))
                yield from self.consume_internal_steps_rec(label_ext)
        else:
            yield label

    def psi_internal(self, label: Label[F]):
        label_extensions = self.consume_internal_steps(label)
        if label_extensions:
            for label_ext in label_extensions:
                label_ext = self.add_label(label_ext)
                self.add_transition(label, label_ext, Internal())

    def find_new_pairs(self) -> Iterable[Pair[F]]:
        tmp_pairs: set[Pair[F]] = set()
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

        return iter(tmp_pairs)

    def fix(self):
        # the initial labels are built outside the engine: register them before anything refers to them
        self.initial_pairs = {self.canonical_pair(pair) for pair in self.initial_pairs}
        self.start_labels = {self.canonical(label) for label in self.start_labels}
        for pair in self.initial_pairs:
            self.add_pair(pair)

        qp: deque[Pair[F]] = deque(self.initial_pairs)
        ql: deque[Label[F]] = deque(self.start_labels)

        visited: set[Label[F] | Pair[F]] = set()

        def qlappend(label: Label[F]):
            if label not in visited:
                ql.append(label)
                visited.add(label)

        def qpappend(pair: Pair[F]):
            if pair not in visited:
                qp.append(pair)
                visited.add(pair)


        while (qp or ql):
            while ql:
                label = ql.popleft()

                self.psi_internal(label)

            while qp:
                pair = qp.popleft()

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
