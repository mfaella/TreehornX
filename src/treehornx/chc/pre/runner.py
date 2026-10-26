"""Bottom-up run of a symbolic data tree automaton (SDTA) over the backbone of the knitted-trees.

The runner is generic over the state `NS` of a node (a Lab label, or a label with more information such as
its taints). A predicate `<name><ID>` is attached to every node state (POPL, Sec. 5, Fig. 4). Its arguments
are the data symbols of the label, the automaton state of the node and the flag `e`, true when some node of
the subtree is an error according to `is_error`, or some link between a node of the subtree and one of its
children is an error according to `is_pair_error` (it raises the flag of the parent). Its clauses carry every
data constraint of the node and of the links to its children, so they are the whole system: the steps of the
lace have no clauses of their own.

The children of a node are collected one at a time instead of in a single clause over their product: the
predicate `<name><ID>_<N>` holds the data of the node, the states of the first N children read by ψ and the
error flag accumulated so far, and `<name><ID>` follows from `<name><ID>_<k+m>` through ψ.
Symbols of the parent are prefixed with `p`, those of the j-th child with `c<j>` (children indexed from 0):
data symbols as `p_v0_1`, `c0_f0_1`,
states as `pre_p_<STATE>`, `pre_c<j>_<STATE>`, and the flag as `pre_p_e`, `pre_c<j>_e`; the flag accumulated
over the first N children is `pre_p_e<N>`.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from typing import Generic, Iterable, Iterator, Literal, TypeVar

from treehornx import ir
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.core.InternedPool import InternedPool
from treehornx.enum_models.core.Pair import Pair


NS = TypeVar("NS")

ERROR_FLAG = "e"
PARENT = "p"


def child_role(j: int) -> str:
    return f"c{j}"


def data_prefix(role: str) -> str:
    return f"{role}_"


def disjunction(*args: sx.SExpr) -> sx.SExpr:
    """The disjunction of `args`, simplified when one of them is a constant."""
    if sx.TRUE in args:
        return sx.TRUE
    args = tuple(a for a in args if a != sx.FALSE)
    if not args:
        return sx.FALSE
    return args[0] if len(args) == 1 else sx.OpExpr(sx.Operator.OR, *args)


@dataclass
class BotUpAutomataRunner(ABC, Generic[NS]):
    function: ir.Function
    pairs: Iterable[Pair[NS]]
    ctx: SDTAContext
    k: int
    m: int
    name: str = "Pre"
    accept_empty: bool = True
    """ψ_F on the nil state, checked when the root is not an input node (empty input tree)."""
    _label_ids: InternedPool[NS] = field(default_factory=InternedPool[NS], init=False)

    def __post_init__(self) -> None:
        assert ERROR_FLAG not in self.ctx.states, f"the state name '{ERROR_FLAG}' is reserved for the error flag"
        self.pairs = list(self.pairs)
        # labels are numbered in the order of the pairs, so predicates and clauses come out in a fixed order
        for pair in self.pairs:
            self._label_ids.intern(pair.parent)
            self._label_ids.intern(pair.child)

    @abstractmethod
    def is_error(self, label: NS, prefix: str) -> sx.SExpr:
        """Whether `label` is an error. It may read the data symbols of the node, prefixed by `prefix`."""

    @abstractmethod
    def is_input_node(self, label: NS) -> bool:
        """Whether the node belongs to the input tree of the automaton; otherwise its state is nil."""

    @abstractmethod
    def is_input_child(self, parent: NS, j: int) -> bool:
        """Whether the j-th child of `parent` is an input node: decided by the parent, so the arguments of
        `<name><ID>_<N>` do not depend on the children collected."""

    @abstractmethod
    def is_root(self, label: NS) -> bool: ...

    def is_pair_error(self, parent: NS, child: NS, j: int, parent_prefix: str, child_prefix: str) -> sx.SExpr:
        """Whether the link between `parent` and its j-th child is an error: it raises the flag of the parent.
        It may read the data symbols of both nodes; no pair is an error by default."""
        return sx.FALSE

    # -----------------------------------------------------------------------
    # symbols
    # -----------------------------------------------------------------------

    def _smt_type(self, state: str) -> sx.Type:
        return sx.Type.Int if self.ctx.states[state] == "int" else sx.Type.Bool

    def state_symbols(self, role: str) -> dict[str, sx.Var]:
        return {state: sx.Var(f"pre_{role}_{state}", self._smt_type(state)) for state in self.ctx.states}

    def error_symbol(self, role: str) -> sx.Var:
        return sx.Var(f"pre_{role}_{ERROR_FLAG}", sx.Type.Bool)

    def chain_error_symbol(self, n: int) -> sx.Var:
        """The error flag accumulated over the parent and its first `n` children."""
        return sx.Var(f"pre_{PARENT}_{ERROR_FLAG}{n}", sx.Type.Bool)

    # The data of a node, the constraints between them and the consistency between a parent and its j-th
    # child: implemented by the runner attached to each kind of label.

    @abstractmethod
    def node_data_symbols(self, label: NS, prefix: str) -> list[sx.Var]: ...

    @abstractmethod
    def node_data_types(self, label: NS) -> list[sx.Type]: ...

    @abstractmethod
    def node_field_symbol(self, field_id: int, index: int, prefix: str) -> sx.Var:
        """The data field `field_id` of the node at the frame `index`."""

    @abstractmethod
    def node_consistency(
        self, parent: NS, child: NS, j: int, parent_prefix: str, child_prefix: str
    ) -> list[sx.SExpr]: ...

    @abstractmethod
    def node_local_constraints(self, label: NS, prefix: str) -> list[sx.SExpr]:
        """Constraints between the frames of `label`, including those dropped from its arguments."""

    def _label_id(self, label: NS) -> int:
        return self._label_ids.get_id(label)

    def _args(self, label: NS, role: str) -> list[sx.Var]:
        data = self.node_data_symbols(label, data_prefix(role))
        return [*data, *self.state_symbols(role).values(), self.error_symbol(role)]

    def _arg_types(self, label: NS) -> list[sx.Type]:
        data_types = self.node_data_types(label)
        return [*data_types, *(self._smt_type(state) for state in self.ctx.states), sx.Type.Bool]

    def predicate(self, label: NS) -> sx.Predicate:
        return sx.Predicate(f"{self.name}{self._label_id(label)}", self._arg_types(label))

    def apply(self, label: NS, role: str) -> sx.Application:
        return sx.Application(self.predicate(label), *self._args(label, role))

    def _stored_children(self, parent: NS, n: int) -> list[int]:
        """The children among the first `n` whose states are read by ψ."""
        return [j for j in range(min(n, self.k)) if self.is_input_child(parent, j)]

    def chain_predicate(self, parent: NS, n: int) -> sx.Predicate:
        states = [self._smt_type(state) for _ in self._stored_children(parent, n) for state in self.ctx.states]
        types = [*self.node_data_types(parent), *states, sx.Type.Bool]
        return sx.Predicate(f"{self.name}{self._label_id(parent)}_{n}", types)

    def chain_apply(self, parent: NS, n: int) -> sx.Application:
        data = self.node_data_symbols(parent, data_prefix(PARENT))
        states = [s for j in self._stored_children(parent, n) for s in self.state_symbols(child_role(j)).values()]
        return sx.Application(self.chain_predicate(parent, n), *data, *states, self.chain_error_symbol(n))

    # -----------------------------------------------------------------------
    # backbone
    # -----------------------------------------------------------------------

    @cached_property
    def children(self) -> dict[NS, dict[int, set[NS]]]:
        index: dict[NS, dict[int, set[NS]]] = defaultdict(lambda: defaultdict(set))
        for pair in self.pairs:
            index[pair.parent][pair.j].add(pair.child)
        return index

    @cached_property
    def labels(self) -> set[NS]:
        return {pair.parent for pair in self.pairs} | {pair.child for pair in self.pairs}

    def is_leaf(self, label: NS) -> bool:
        return label not in self.children and not self.is_input_node(label) and not self.is_root(label)

    # -----------------------------------------------------------------------
    # clauses
    # -----------------------------------------------------------------------

    def leaf_clause(self, label: NS) -> sx.Clause:
        """Pre1: an auxiliary leaf has the nil state."""
        error = sx.OpExpr(sx.Operator.EQ, self.error_symbol(PARENT), self.is_error(label, data_prefix(PARENT)))
        body: list[sx.SExpr | sx.Application] = [*self.node_local_constraints(label, data_prefix(PARENT)), error]
        return sx.Clause(self.apply(label, PARENT), *body)

    def _psi(self, parent: NS) -> sx.SExpr:
        children_states = {
            self.function.node.pointer_fields[j].name: (
                self.state_symbols(child_role(j)) if self.is_input_child(parent, j) else None
            )
            for j in range(self.k)
        }
        fields = {f.name: self.node_field_symbol(f.id, 1, data_prefix(PARENT)) for f in self.function.node.data_fields}
        return self.ctx.psi(children_states, fields, self.state_symbols(PARENT))

    def init_clause(self, parent: NS) -> sx.Clause:
        """PreInit: no child collected yet, the flag is the error of the parent."""
        error = sx.OpExpr(sx.Operator.EQ, self.chain_error_symbol(0), self.is_error(parent, data_prefix(PARENT)))
        body: list[sx.SExpr | sx.Application] = [*self.node_local_constraints(parent, data_prefix(PARENT)), error]
        return sx.Clause(self.chain_apply(parent, 0), *body)

    def collect_clause(self, parent: NS, child: NS, j: int) -> sx.Clause:
        """PreCollect: the j-th child is collected, its data are projected away. The flag of the parent also
        collects the error of the child and the error of the pair."""
        assert self.is_input_node(child) == self.is_input_child(parent, j)
        role = child_role(j)
        parent_prefix, child_prefix = data_prefix(PARENT), data_prefix(role)
        error = disjunction(
            self.chain_error_symbol(j),
            self.error_symbol(role),
            self.is_pair_error(parent, child, j, parent_prefix, child_prefix),
        )
        body: list[sx.SExpr | sx.Application] = [
            self.chain_apply(parent, j),
            self.apply(child, role),
            *self.node_local_constraints(child, child_prefix),
            *self.node_consistency(parent, child, j, parent_prefix, child_prefix),
            sx.OpExpr(sx.Operator.EQ, self.chain_error_symbol(j + 1), error),
        ]
        return sx.Clause(self.chain_apply(parent, j + 1), *body)

    def node_clause(self, parent: NS) -> sx.Clause:
        """Pre2: the state of an input node follows from the states of its children through ψ."""
        last = self.k + self.m
        body: list[sx.SExpr | sx.Application] = [self.chain_apply(parent, last)]
        if self.is_input_node(parent):
            body.append(self._psi(parent))
        body.append(sx.OpExpr(sx.Operator.EQ, self.error_symbol(PARENT), self.chain_error_symbol(last)))
        return sx.Clause(self.apply(parent, PARENT), *body)

    def _has_all_children(self, parent: NS) -> bool:
        by_child = self.children.get(parent)
        return by_child is not None and all(j in by_child for j in range(self.k + self.m))

    def node_clauses(self, parent: NS) -> Iterable[sx.Clause]:
        if not self._has_all_children(parent):
            return
        yield self.init_clause(parent)
        by_child = self.children[parent]
        for j in range(self.k + self.m):
            for child in sorted(by_child[j], key=self._label_id):
                yield self.collect_clause(parent, child, j)
        yield self.node_clause(parent)

    def query(self, root: NS) -> sx.Clause:
        """PreQ: an accepted input tree leads to an error."""
        if self.is_input_node(root):
            accepted = self.ctx.psiF(self.state_symbols(PARENT))
        else:
            accepted = sx.Constant(self.accept_empty)
        body: list[sx.SExpr | sx.Application] = [
            self.apply(root, PARENT),
            *self.node_local_constraints(root, data_prefix(PARENT)),
            self.error_symbol(PARENT),
            accepted,
        ]
        return sx.Clause(False, *body)

    def predicates(self) -> list[sx.Predicate]:
        predicates: list[sx.Predicate] = []
        for label in sorted(self.labels, key=self._label_id):
            predicates.append(self.predicate(label))
            if self._has_all_children(label):
                predicates.extend(self.chain_predicate(label, n) for n in range(self.k + self.m + 1))
        return predicates

    def clauses(self) -> Iterator[sx.Clause]:
        """Generated lazily, one parent at a time."""
        for label in sorted(self.labels, key=self._label_id):
            if label in self.children:
                yield from self.node_clauses(label)
            elif self.is_leaf(label):
                yield self.leaf_clause(label)

    def queries(self) -> list[sx.Clause]:
        roots = (label for label in sorted(self.labels, key=self._label_id) if self.is_root(label))
        return [self.query(root) for root in roots]
