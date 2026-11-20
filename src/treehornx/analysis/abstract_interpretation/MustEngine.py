"""Must information of the states of a symbolic tree, computed bottom-up and then top-down.

The values are ordered by their concrete states, as usual in abstract interpretation: a lower value describes fewer
concrete states, so it has more facts. `BOTTOM` (⊥) is `false`: no derivation (found yet). The subclasses give:

* `meet` (⊓): the conjunction of the facts of one derivation (a parent, a child and their edge). It returns `BOTTOM`
  when the facts clash (for example, two different constants in one class).
* `join` (⊔): the facts common to alternative derivations. It never clashes.
* `project`: forgets the symbols outside the given ones (the value goes up).
* `with_role`: renames the symbols of a value to a role (`None`, `Parent()`, `Slot(j)`).

**Bottom-up pass.** `_bu_result[s]` holds in every finite derivation of the subtree of `s`. A leaf has its own facts.
For the other states, the engine starts from the facts of `s` and takes its slots one at a time, in index order. For
slot j, each alternative child c gives the meet of the current value, the result of c and the facts of the edge,
projected onto the arguments of `s`; an alternative that clashes is dropped. The join of the alternatives is the
current value for the next slot. A slot with no alternative left gives `BOTTOM`.

**Top-down pass** (with `top_down`). `_td_result[s]` holds in every complete derivation, from a root down to leaves,
that contains `s` (its context and its subtree). A root has the empty context, so it keeps its bottom-up result. For
the other states, each parent p (slot j) gives the meet of the top-down result of p, the bottom-up result of `s` and
the facts of the edge, projected onto the arguments of `s`. The result is the join over the parents. The bottom-up
result of `s` is met with each context before the join: this is more precise than a meet after the join, and the
facts of the siblings reach `s` through the bottom-up result of its parent.

Both passes compute a least fixpoint: the values start at `BOTTOM` and only go up. When a result changes, the states
that read it are computed again. The subclasses must make `meet`, `join` and `project` monotone, and F must have no
infinite ascending chains, otherwise the fixpoint may not terminate on trees with cycles.

`result(s)` is the top-down result of `s` when there is one, else its bottom-up result, else the facts of `s`.
`outputs()` replaces every state `s` with `apply(s, result(s))`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Generic, Iterable, TypeVar, final

from typing_extensions import override

from treehornx.analysis.commons.ConstrTLab import ConstrTLab
from treehornx.analysis.constraints.symbols import Parent, Role, Slot
from treehornx.symbolic_tree import Edge, SymbolicTree
from treehornx.intern import intern
from treehornx.smt import Var

F = TypeVar("F")


@intern
@dataclass(slots=True)
class Bottom:
    """The type of `BOTTOM` (⊥, `false`): no derivation. It has the single instance `BOTTOM`."""

    if TYPE_CHECKING:

        @staticmethod
        def make() -> Bottom: ...


BOTTOM = Bottom.make()


@dataclass
class MustEngine(ABC, Generic[F]):
    tree: SymbolicTree[ConstrTLab]
    """The input: the states and the edges to visit."""
    top_down: bool = True
    """After the bottom-up pass, also run the top-down pass (the facts of the complete derivations of each state)."""

    _fixed: bool = field(default=False, init=False)
    _bu_result: dict[ConstrTLab, F | Bottom] = field(init=False)
    """Bottom-up result of every state: the facts of all the finite derivations of its subtree; `BOTTOM`: no feasible
    finite derivation (found yet)."""
    _td_result: dict[ConstrTLab, F | Bottom] = field(init=False)
    """Top-down result of every state: the facts at the state in all the complete derivations (from a root down to
    leaves) that contain it; `BOTTOM`: no such derivation (found yet)."""
    _children_by_parent_slot: dict[tuple[ConstrTLab, int], set[ConstrTLab]] = field(init=False)
    """(parent, j) → the alternative children of slot j."""
    _parent_slot_by_child: dict[ConstrTLab, set[tuple[ConstrTLab, int]]] = field(init=False)
    """child → the pairs (parent, j) where it is the child of slot j."""

    @abstractmethod
    def meet(self, *ds: F) -> F | Bottom:
        """⊓: the conjunction of `ds` (facts of one derivation); `BOTTOM` when they clash."""

    @abstractmethod
    def join(self, *ds: F) -> F:
        """⊔: the facts common to all of `ds` (alternative derivations)."""

    @abstractmethod
    def project(self, f: F, variables: Iterable[Var]) -> F:
        """The facts of `f` on `variables` only (the others are forgotten)."""

    @abstractmethod
    def with_role(self, facts: F, role: Role | None) -> F:
        """`facts` with their symbols renamed to `role`."""

    @abstractmethod
    def apply(self, s: ConstrTLab, d: F) -> ConstrTLab:
        """The state `s` rewritten with its result `d`."""

    @abstractmethod
    def no_facts(self) -> F:
        """The fact that holds no information: `apply(s, no_facts())` keeps the constraints of `s` and gives it the
        type of the other outputs."""

    @abstractmethod
    def label_facts(self, lab: ConstrTLab, role: Role | None = None) -> F | Bottom:
        """The facts of the constraints of `lab`, with the symbols of `role`; `BOTTOM` when they clash."""

    @abstractmethod
    def edge_facts(self, e: Edge[ConstrTLab]) -> F | Bottom:
        """The facts of the consistency constraints of `e` (parent with `Parent()`, child with `Slot(e.j)`); `BOTTOM`
        when they clash."""

    def _meet(self, *facts: F | Bottom) -> F | Bottom:
        """`meet` extended to `BOTTOM`: `BOTTOM` when one of `facts` is `BOTTOM`."""
        values: list[F] = [f for f in facts if not isinstance(f, Bottom)]
        if len(values) < len(facts):
            return BOTTOM
        return self.meet(*values)

    def _join(self, *facts: F | Bottom) -> F | Bottom:
        """`join` extended to `BOTTOM`: `BOTTOM` is neutral; `BOTTOM` when all of `facts` are `BOTTOM` (or none)."""
        values: list[F] = [f for f in facts if not isinstance(f, Bottom)]
        if not values:
            return BOTTOM
        return self.join(*values)

    def equal(self, a: F, b: F) -> bool:
        """True when `a` and `b` are the same facts (by default `==`; override it when F has no value equality)."""
        return a == b

    def _equal(self, a: F | Bottom, b: F | Bottom) -> bool:
        if isinstance(a, Bottom) or isinstance(b, Bottom):
            return a is b
        return self.equal(a, b)

    def _with_role(self, facts: F | Bottom, role: Role | None) -> F | Bottom:
        return BOTTOM if isinstance(facts, Bottom) else self.with_role(facts, role)

    def _bu_init(self) -> None:
        self._bu_result = {
            label: self.label_facts(label) if label in self.tree.leaves else BOTTOM for label in self.tree.labels
        }
        self._children_by_parent_slot = {}
        self._parent_slot_by_child = {}
        for edge in self.tree.edges:
            self._children_by_parent_slot.setdefault((edge.parent, edge.j), set()).add(edge.child)
            self._parent_slot_by_child.setdefault(edge.child, set()).add((edge.parent, edge.j))

    def _bu_compute_state(self, parent: ConstrTLab) -> F | Bottom:
        current: F | Bottom = self.label_facts(parent, Parent())
        if isinstance(current, Bottom):
            return BOTTOM  # the constraints of the parent clash
        for j in range(self.tree.arity):
            alternatives: list[F | Bottom] = []
            for child in self._children_by_parent_slot.get((parent, j), ()):
                alt = self._meet(
                    current,
                    self._with_role(self._bu_result[child], Slot(j)),
                    self.edge_facts(Edge(parent, child, j)),
                )
                if isinstance(alt, Bottom):
                    continue  # the child cannot complete the parent
                alternatives.append(self.project(alt, parent.args(Parent())))
            current = self._join(*alternatives)
            if isinstance(current, Bottom):
                return BOTTOM
        return self._with_role(current, None)

    def _td_init(self) -> None:
        self._td_result = {
            label: self._bu_result[label] if label in self.tree.roots else BOTTOM for label in self.tree.labels
        }

    def _td_compute_state(self, child: ConstrTLab) -> F | Bottom:
        bu = self._bu_result[child]
        if child in self.tree.roots:
            return bu  # the empty context
        if isinstance(bu, Bottom):
            return BOTTOM  # no finite derivation below the child
        alternatives: list[F | Bottom] = []
        for parent, j in self._parent_slot_by_child.get(child, ()):
            alt = self._meet(
                self._with_role(self._td_result[parent], Parent()),  # BOTTOM when the parent is not reached
                self._with_role(bu, Slot(j)),
                self.edge_facts(Edge(parent, child, j)),
            )
            if isinstance(alt, Bottom):
                continue
            alternatives.append(self.with_role(self.project(alt, child.args(Slot(j))), None))
        return self._join(*alternatives)

    def _worklist(
        self,
        start: Iterable[ConstrTLab],
        compute: Callable[[ConstrTLab], F | Bottom],
        results: dict[ConstrTLab, F | Bottom],
        next_states: Callable[[ConstrTLab], Iterable[ConstrTLab]],
    ) -> None:
        """Computes the states of `start`; when the result of a state changes, it stores it and computes
        `next_states` of the state again. Stops when no result changes (each result only goes up from `BOTTOM`,
        finitely many times)."""
        pending: deque[ConstrTLab] = deque()
        queued: set[ConstrTLab] = set()

        def enqueue(labels: Iterable[ConstrTLab]) -> None:
            for s in labels:
                if s not in queued:
                    queued.add(s)
                    pending.append(s)

        enqueue(start)
        while pending:
            state = pending.popleft()
            queued.discard(state)
            new_result = compute(state)
            if not self._equal(new_result, results[state]):
                results[state] = new_result
                enqueue(next_states(state))

    def _parents(self, state: ConstrTLab) -> Iterable[ConstrTLab]:
        return (parent for parent, _ in self._parent_slot_by_child.get(state, ()))

    def _children(self, state: ConstrTLab) -> Iterable[ConstrTLab]:
        for j in range(self.tree.arity):
            yield from self._children_by_parent_slot.get((state, j), ())

    def _fix(self) -> None:
        """Bottom-up pass from the parents of the leaves, then (with `top_down`) the top-down pass from the roots."""
        self._bu_init()
        self._worklist(
            (p for leaf in self.tree.leaves for p in self._parents(leaf)),
            self._bu_compute_state,
            self._bu_result,
            self._parents,
        )
        if self.top_down:
            self._td_init()
            self._worklist(
                (c for root in self.tree.roots for c in self._children(root)),
                self._td_compute_state,
                self._td_result,
                self._children,
            )
        self._fixed = True

    def result(self, label: ConstrTLab) -> F | Bottom:
        """The top-down result of `label` when there is one, else its bottom-up result, else its own facts (`BOTTOM`
        when they clash)."""
        if not self._fixed:
            self._fix()
        if self.top_down and not isinstance(td := self._td_result[label], Bottom):
            return td
        if not isinstance(bu := self._bu_result[label], Bottom):
            return bu
        return self.label_facts(label)

    def outputs(self) -> SymbolicTree[ConstrTLab]:
        def rewrite(s: ConstrTLab) -> ConstrTLab:
            d = self.result(s)
            # a state without a feasible derivation keeps its constraints, in the same wrapper as the others
            return self.apply(s, self.no_facts() if isinstance(d, Bottom) else d)

        return self.tree.map(lambda _, s: rewrite(s))
