"""Postcondition under a precondition (Hoare triple, POPL Sec. 8).

The precondition automaton runs bottom-up over the DFS labels, which carry the complete Lab label of their node:
its input data are the first frames of the Lab labels, as in `PreRunner`. A node is an error when its DFS lace
ends with a violation of the output (tree shape, acceptance of the negated postcondition, bound overflow), or
when the lace ends at `exit` there with an empty output accepted by the negated postcondition. The root query
fires only for input trees accepted by the precondition.
"""

from dataclasses import dataclass, field
from typing import override

import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx.chc.Lab.clauses import consistency_constraint
from treehornx.chc.post.clauses import dfs_consistency, is_overflow, is_violation
from treehornx.chc.post.symbols import dfs_apply, dfs_arg_types, dfs_label_symbols
from treehornx.chc.pre.runner import BotUpAutomataRunner
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.enum_models.Dfs import Dfs, DfsFrame, clean_end, sigma_of
from treehornx.enum_models.Lab.initial import is_initial


@dataclass
class PostUnderPreRunner(BotUpAutomataRunner[DfsFrame]):
    post: SDTAContext | None = field(kw_only=True)
    """Negation of the postcondition, None to check only the tree shape of the output."""
    n_dfs: int = field(kw_only=True)
    accept_nil: bool = field(default=False, kw_only=True)
    check_overflow: bool = field(default=True, kw_only=True)

    @override
    def node_data_symbols(self, label: Dfs, prefix: str) -> list[FNode]:
        return dfs_label_symbols(self.function, self.post, label, prefix)

    @override
    def node_data_types(self, label: Dfs) -> list[smtty.PySMTType]:
        return dfs_arg_types(self.function, self.post, label)

    @override
    def node_apply(self, label: Dfs, prefix: str) -> FNode:
        return dfs_apply(self.function, self.post, label, prefix)

    @override
    def node_consistency(self, parent: Dfs, child: Dfs, parent_prefix: str, child_prefix: str) -> FNode:
        lab = consistency_constraint(self.function, sigma_of(parent), sigma_of(child), parent_prefix, child_prefix)
        if self.post is None:
            return lab
        return smt.And(lab, dfs_consistency(self.function, self.post, parent, child, parent_prefix, child_prefix))

    def _empty_output(self, label: Dfs) -> bool:
        sigma = sigma_of(label)
        return self.accept_nil and clean_end(self.function, sigma) and sigma.frame.isnil[self.function.ROOT]

    @override
    def is_error(self, label: Dfs) -> FNode:
        overflow = self.check_overflow and is_overflow(self.n_dfs, label)
        return smt.Bool(is_violation(self.post, label) or overflow or self._empty_output(label))

    @override
    def is_input_node(self, label: Dfs) -> bool:
        return sigma_of(label)[1].active

    @override
    def is_root(self, label: Dfs) -> bool:
        return is_initial(sigma_of(label))
