"""Precondition layer: the SDTA of the precondition runs on the input tree stored in the first frames."""

from dataclasses import dataclass, field
from typing import override

import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.pre.runner import BotUpAutomataRunner
from treehornx.enum_models.Lab import ERR, OOM, Frame, Lab
from treehornx.enum_models.Lab.initial import is_initial


@dataclass
class PreRunner(BotUpAutomataRunner[Frame]):
    n: int = field(kw_only=True)
    exit_codes: frozenset[ExitCodeKind] = field(default=frozenset({ExitCodeKind.ERR}), kw_only=True)

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
