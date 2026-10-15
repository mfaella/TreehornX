"""Bottom-up run of a symbolic data tree automaton (SDTA) over the backbone of the knitted-trees.

A companion predicate `<name><ID>` is attached to every label (POPL, Sec. 5, Fig. 4). Its arguments are
the data symbols of the Lab predicate, the automaton state of the node and the flag `e`, true when some
node of the subtree is an error according to `is_error`. Symbols of the parent are prefixed with `p`,
those of the j-th child with `c<j>` (children indexed from 0): data symbols as `p_v0_1`, `c0_f0_1`,
states as `pre_p_<STATE>`, `pre_c<j>_<STATE>`, and the flag as `pre_p_e`, `pre_c<j>_e`.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from itertools import product
from typing import Any, Iterable, cast

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.clauses import consistency_constraint
from treehornx.chc.Lab.symbols import apply as lab_apply
from treehornx.chc.Lab.symbols import field_symbol, frame_types, kept_frames, label_symbols
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair

ERROR_FLAG = "e"
PARENT = "p"


def child_role(j: int) -> str:
    return f"c{j}"


def data_prefix(role: str) -> str:
    return f"{role}_"


@dataclass
class BotUpAutomataRunner[F](ABC):
    function: ir.Function
    pairs: Iterable[Pair[F]]
    ctx: SDTAContext
    k: int
    m: int
    name: str = "Pre"
    accept_empty: bool = True
    """ψ_F on the nil state, checked when the root is not an input node (empty input tree)."""

    def __post_init__(self) -> None:
        assert ERROR_FLAG not in self.ctx.states, f"the state name '{ERROR_FLAG}' is reserved for the error flag"
        self.pairs = list(self.pairs)

    @abstractmethod
    def is_error(self, label: Label[F]) -> FNode:
        """Whether the enumerated part of `label` is an error."""

    @abstractmethod
    def is_input_node(self, label: Label[F]) -> bool:
        """Whether the node belongs to the input tree of the automaton; otherwise its state is nil."""

    @abstractmethod
    def is_root(self, label: Label[F]) -> bool: ...

    # -----------------------------------------------------------------------
    # symbols
    # -----------------------------------------------------------------------

    def _smt_type(self, state: str) -> smtty.PySMTType:
        return smtty.INT if self.ctx.states[state] == "int" else smtty.BOOL

    def state_symbols(self, role: str) -> dict[str, FNode]:
        return {state: smt.Symbol(f"pre_{role}_{state}", self._smt_type(state)) for state in self.ctx.states}

    def error_symbol(self, role: str) -> FNode:
        return smt.Symbol(f"pre_{role}_{ERROR_FLAG}", smtty.BOOL)

    def _data_symbols(self, label: Label[F], role: str) -> list[FNode]:
        return label_symbols(self.function, cast(Any, label), data_prefix(role))

    def _lab(self, label: Label[F], role: str) -> FNode:
        return lab_apply(self.function, cast(Any, label), data_prefix(role))

    def _args(self, label: Label[F], role: str) -> list[FNode]:
        return [*self._data_symbols(label, role), *self.state_symbols(role).values(), self.error_symbol(role)]

    def _arg_types(self, label: Label[F]) -> list[smtty.PySMTType]:
        data_types = [t for _ in kept_frames(cast(Any, label)) for t in frame_types(self.function)]
        return [*data_types, *(self._smt_type(state) for state in self.ctx.states), smtty.BOOL]

    def predicate(self, label: Label[F]) -> FNode:
        return chc.Predicate(f"{self.name}{label.id}", self._arg_types(label))

    def apply(self, label: Label[F], role: str) -> FNode:
        return chc.Apply(self.predicate(label), self._args(label, role))

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

    def leaf_clause(self, label: Label[F]) -> FNode:
        """Pre1: an auxiliary leaf has the nil state."""
        body = smt.And(self._lab(label, PARENT), smt.Iff(self.error_symbol(PARENT), self.is_error(label)))
        return chc.Clause(body, self.apply(label, PARENT))

    def _psi(self, parent: Label[F], children: tuple[Label[F], ...]) -> FNode:
        children_states = {
            self.function.node.pointer_fields[j].name: (
                self.state_symbols(child_role(j)) if self.is_input_node(children[j]) else None
            )
            for j in range(self.k)
        }
        fields = {
            f.name: field_symbol(self.function, f.id, 1, data_prefix(PARENT)) for f in self.function.node.data_fields
        }
        return self.ctx.psi(children_states, fields, self.state_symbols(PARENT))

    def node_clause(self, parent: Label[F], children: tuple[Label[F], ...]) -> FNode:
        """Pre2: the state of an input node follows from the states of its children through ψ."""
        body = [self._lab(parent, PARENT)]
        for j, child in enumerate(children):
            body.append(self.apply(child, child_role(j)))
            body.append(
                consistency_constraint(
                    self.function, cast(Any, parent), cast(Any, child), data_prefix(PARENT), data_prefix(child_role(j))
                )
            )
        if self.is_input_node(parent):
            body.append(self._psi(parent, children))
        errors = [self.error_symbol(child_role(j)) for j in range(len(children))]
        body.append(smt.Iff(self.error_symbol(PARENT), smt.Or(*errors, self.is_error(parent))))
        return chc.Clause(smt.And(*body), self.apply(parent, PARENT))

    def node_clauses(self, parent: Label[F]) -> Iterable[FNode]:
        by_child = self.children[parent]
        if any(j not in by_child for j in range(self.k + self.m)):
            return
        for children in product(*(sorted(by_child[j], key=lambda lab: lab.id) for j in range(self.k + self.m))):
            yield self.node_clause(parent, children)

    def query(self, root: Label[F]) -> FNode:
        """PreQ: an accepted input tree leads to an error."""
        if self.is_input_node(root):
            accepted = self.ctx.psiF(self.state_symbols(PARENT))
        else:
            accepted = smt.Bool(self.accept_empty)
        body = smt.And(self.apply(root, PARENT), self.error_symbol(PARENT), accepted)
        return chc.Clause(body, smt.FALSE())

    def predicates(self) -> list[FNode]:
        return [self.predicate(label) for label in sorted(self.labels, key=lambda lab: lab.id)]

    def clauses(self) -> list[FNode]:
        clauses: list[FNode] = []
        for label in sorted(self.labels, key=lambda lab: lab.id):
            if label in self.children:
                clauses.extend(self.node_clauses(label))
            elif self.is_leaf(label):
                clauses.append(self.leaf_clause(label))
        return clauses

    def queries(self) -> list[FNode]:
        return [self.query(label) for label in sorted(self.labels, key=lambda lab: lab.id) if self.is_root(label)]
