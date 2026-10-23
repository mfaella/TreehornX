"""Bottom-up run of a symbolic data tree automaton (SDTA) over the backbone of the knitted-trees.

A predicate `<name><ID>` is attached to every label (POPL, Sec. 5, Fig. 4). Its arguments are the data
symbols of the label, the automaton state of the node and the flag `e`, true when some node of the subtree
is an error according to `is_error`. Its clauses carry every data constraint of the node and of the links
to its children, so they are the whole system: the steps of the lace have no clauses of their own.
Symbols of the parent are prefixed with `p`, those of the j-th child with `c<j>` (children indexed from 0):
data symbols as `p_v0_1`, `c0_f0_1`,
states as `pre_p_<STATE>`, `pre_c<j>_<STATE>`, and the flag as `pre_p_e`, `pre_c<j>_e`.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from itertools import product
from typing import Generic, Iterable, Iterator, Literal, TypeVar

from treehornx import ir
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.core.InternedPool import InternedPool
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair


F = TypeVar("F")

ERROR_FLAG = "e"
PARENT = "p"


def child_role(j: int) -> str:
    return f"c{j}"


def data_prefix(role: str) -> str:
    return f"{role}_"


@dataclass
class BotUpAutomataRunner(ABC, Generic[F]):
    function: ir.Function
    pairs: Iterable[Pair[Label[F]]]
    ctx: SDTAContext
    k: int
    m: int
    name: str = "Pre"
    accept_empty: bool = True
    """ψ_F on the nil state, checked when the root is not an input node (empty input tree)."""
    _label_ids: InternedPool[Label[F]] = field(default_factory=InternedPool[Label[F]], init=False)

    def __post_init__(self) -> None:
        assert ERROR_FLAG not in self.ctx.states, f"the state name '{ERROR_FLAG}' is reserved for the error flag"
        self.pairs = list(self.pairs)
        # labels are numbered in the order of the pairs, so predicates and clauses come out in a fixed order
        for pair in self.pairs:
            self._label_ids.intern(pair.parent)
            self._label_ids.intern(pair.child)

    @abstractmethod
    def is_error(self, label: Label[F]) -> sx.SExpr:
        """Whether the enumerated part of `label` is an error."""

    @abstractmethod
    def is_input_node(self, label: Label[F]) -> bool:
        """Whether the node belongs to the input tree of the automaton; otherwise its state is nil."""

    @abstractmethod
    def is_root(self, label: Label[F]) -> bool: ...

    # -----------------------------------------------------------------------
    # symbols
    # -----------------------------------------------------------------------

    def _smt_type(self, state: str) -> sx.Type:
        return sx.Type.Int if self.ctx.states[state] == "int" else sx.Type.Bool

    def state_symbols(self, role: str) -> dict[str, sx.Var]:
        return {state: sx.Var(f"pre_{role}_{state}", self._smt_type(state)) for state in self.ctx.states}

    def error_symbol(self, role: str) -> sx.Var:
        return sx.Var(f"pre_{role}_{ERROR_FLAG}", sx.Type.Bool)

    # The data of a node, the constraints between them and the consistency between a parent and its j-th
    # child: implemented by the runner attached to each kind of label.

    @abstractmethod
    def node_data_symbols(self, label: Label[F], prefix: str) -> list[sx.Var]: ...

    @abstractmethod
    def node_data_types(self, label: Label[F]) -> list[sx.Type]: ...

    @abstractmethod
    def node_field_symbol(self, field_id: int, index: int, prefix: str) -> sx.Var:
        """The data field `field_id` of the node at the frame `index`."""

    @abstractmethod
    def node_consistency(
        self, parent: Label[F], child: Label[F], j: int, parent_prefix: str, child_prefix: str
    ) -> list[sx.SExpr]: ...

    @abstractmethod
    def node_local_constraints(self, label: Label[F], prefix: str) -> list[sx.SExpr]:
        """Constraints between the frames of `label`, including those dropped from its arguments."""

    def _label_id(self, label: Label[F]) -> int:
        return self._label_ids.get_id(label)

    def _args(self, label: Label[F], role: str) -> list[sx.Var]:
        data = self.node_data_symbols(label, data_prefix(role))
        return [*data, *self.state_symbols(role).values(), self.error_symbol(role)]

    def _arg_types(self, label: Label[F]) -> list[sx.Type]:
        data_types = self.node_data_types(label)
        return [*data_types, *(self._smt_type(state) for state in self.ctx.states), sx.Type.Bool]

    def predicate(self, label: Label[F]) -> sx.Predicate:
        return sx.Predicate(f"{self.name}{self._label_id(label)}", self._arg_types(label))

    def apply(self, label: Label[F], role: str) -> sx.Application:
        return sx.Application(self.predicate(label), *self._args(label, role))

    # -----------------------------------------------------------------------
    # backbone
    # -----------------------------------------------------------------------

    @cached_property
    def children(self) -> dict[Label[F], dict[int, set[Label[F]]]]:
        index: dict[Label[F], dict[int, set[Label[F]]]] = defaultdict(lambda: defaultdict(set))
        for pair in self.pairs:
            index[pair.parent][pair.j].add(pair.child)
        return index

    @cached_property
    def labels(self) -> set[Label[F]]:
        return {pair.parent for pair in self.pairs} | {pair.child for pair in self.pairs}

    def is_leaf(self, label: Label[F]) -> bool:
        return label not in self.children and not self.is_input_node(label) and not self.is_root(label)

    # -----------------------------------------------------------------------
    # clauses
    # -----------------------------------------------------------------------

    def leaf_clause(self, label: Label[F]) -> sx.Clause:
        """Pre1: an auxiliary leaf has the nil state."""
        error = sx.OpExpr(sx.Operator.EQ, self.error_symbol(PARENT), self.is_error(label))
        body: list[sx.SExpr | sx.Application] = [*self.node_local_constraints(label, data_prefix(PARENT)), error]
        return sx.Clause(self.apply(label, PARENT), *body)

    def _psi(self, parent: Label[F], children: tuple[Label[F], ...]) -> sx.SExpr:
        children_states = {
            self.function.node.pointer_fields[j].name: (
                self.state_symbols(child_role(j)) if self.is_input_node(children[j]) else None
            )
            for j in range(self.k)
        }
        fields = {f.name: self.node_field_symbol(f.id, 1, data_prefix(PARENT)) for f in self.function.node.data_fields}
        return self.ctx.psi(children_states, fields, self.state_symbols(PARENT))

    def node_clause(self, parent: Label[F], children: tuple[Label[F], ...]) -> sx.Clause:
        """Pre2: the state of an input node follows from the states of its children through ψ."""
        body: list[sx.SExpr | sx.Application] = [*self.node_local_constraints(parent, data_prefix(PARENT))]
        for j, child in enumerate(children):
            body.append(self.apply(child, child_role(j)))
            body.extend(self.node_local_constraints(child, data_prefix(child_role(j))))
            body.extend(self.node_consistency(parent, child, j, data_prefix(PARENT), data_prefix(child_role(j))))
        if self.is_input_node(parent):
            body.append(self._psi(parent, children))
        # is_error is a constant: true makes the flag true, false is left out of the disjunction
        error = self.is_error(parent)
        errors = [*(self.error_symbol(child_role(j)) for j in range(len(children))), error]
        errors = [e for e in errors if e != sx.FALSE]
        if error == sx.TRUE:
            some_error: sx.SExpr = sx.TRUE
        else:
            some_error = errors[0] if len(errors) == 1 else sx.OpExpr(sx.Operator.OR, *errors)
        body.append(sx.OpExpr(sx.Operator.EQ, self.error_symbol(PARENT), some_error))
        return sx.Clause(self.apply(parent, PARENT), *body)

    def node_clauses(self, parent: Label[F]) -> Iterable[sx.Clause]:
        by_child = self.children[parent]
        if any(j not in by_child for j in range(self.k + self.m)):
            return
        for children in product(*(sorted(by_child[j], key=self._label_id) for j in range(self.k + self.m))):
            yield self.node_clause(parent, children)

    def query(self, root: Label[F]) -> sx.Clause:
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
        return [self.predicate(label) for label in sorted(self.labels, key=self._label_id)]

    def clauses(self) -> Iterator[sx.Clause]:
        """Generated lazily: the product of `node_clauses` can be too large to hold in memory."""
        for label in sorted(self.labels, key=self._label_id):
            if label in self.children:
                yield from self.node_clauses(label)
            elif self.is_leaf(label):
                yield self.leaf_clause(label)

    def queries(self) -> list[sx.Clause]:
        roots = (label for label in sorted(self.labels, key=self._label_id) if self.is_root(label))
        return [self.query(root) for root in roots]
