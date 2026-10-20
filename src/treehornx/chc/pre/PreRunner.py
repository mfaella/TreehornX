"""Precondition layer: the SDTA of the precondition runs on the input tree stored in the first frames."""

from dataclasses import dataclass, field
from typing import override

import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.clauses import consistency_constraint, internal_constraints
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.chc.pre.runner import BotUpAutomataRunner
from treehornx.enum_models.Lab import ERR, OOM, Frame, Lab
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.feature_flags import ENABLE_PRE_INTERNAL_CONSTRAINTS


@dataclass
class PreRunner(BotUpAutomataRunner[Frame]):
    sym: ChcLabUtils = field(kw_only=True)
    n: int = field(kw_only=True)
    exit_codes: frozenset[ExitCodeKind] = field(default=frozenset({ExitCodeKind.ERR}), kw_only=True)

    @override
    def node_data_symbols(self, label: Lab, prefix: str) -> list[FNode]:
        return self.sym.label_symbols(label, prefix)

    @override
    def node_data_types(self, label: Lab) -> list[smtty.PySMTType]:
        return [t for _ in self.sym.kept_frames(label) for t in self.sym.frame_types()]

    @override
    def node_field_symbol(self, field_id: int, index: int, prefix: str) -> FNode:
        return self.sym.field_symbol(field_id, index, prefix)

    @override
    def node_apply(self, label: Lab, prefix: str) -> FNode:
        return self.sym.apply(label, prefix)

    @override
    def node_consistency(self, parent: Lab, child: Lab, j: int, parent_prefix: str, child_prefix: str) -> FNode:
        return consistency_constraint(self.sym, parent, child, j, parent_prefix, child_prefix)

    @override
    def node_local_constraints(self, label: Lab, prefix: str) -> list[FNode]:
        return internal_constraints(self.sym, label, prefix) if ENABLE_PRE_INTERNAL_CONSTRAINTS else []

    def label_exit(self, label: Lab) -> set[ExitCodeKind]:
        """Exit statuses of the frames of the label (label_exit, CAV25 C.3)."""
        statuses: set[ExitCodeKind] = set()
        for f in label[2:]:
            if isinstance(f.event, ERR):
                statuses.add(ExitCodeKind.ERR)
            if isinstance(f.event, OOM):
                statuses.add(ExitCodeKind.OOM)
        if len(label) == self.n + 1:
            statuses.add(ExitCodeKind.LABEL_OVERFLOW)
        return statuses

    @override
    def is_error(self, label: Lab) -> FNode:
        return smt.Bool(bool(self.label_exit(label) & self.exit_codes))

    @override
    def is_input_node(self, label: Lab) -> bool:
        return label[1].active

    @override
    def is_root(self, label: Lab) -> bool:
        return is_initial(label)
