from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, TextIO

from treehornx.chc._internal.CHCFactory import CHCFactory
from treehornx.chc._internal.smtlib import assert_, decl_fun
from treehornx.enum_labels import LaceOverApproximation
from treehornx.enum_labels.core.Dir import Down, Internal, Up
from treehornx.enum_labels.core.Event import ERR, LOF, OOM
from treehornx.enum_labels.core.Label import Label
from treehornx.ir._internal.sorts.Struct import Struct
from treehornx.ir.function import Function


class ExitCodeKind(Enum):
    ERR = 1
    OOM = 2
    LABEL_OVERFLOW = 3


@dataclass
class SMT2ScriptPrinter:
    function: Function
    tree_node_sort: Struct
    lace_over_approx: LaceOverApproximation

    def _query_required(self, lab: Label, exit_code: ExitCodeKind) -> bool:
        match exit_code:
            case ExitCodeKind.ERR:
                return ERR() in lab.frame.events
            case ExitCodeKind.OOM:
                return OOM() in lab.frame.events
            case ExitCodeKind.LABEL_OVERFLOW:
                return LOF() in lab.frame.events

    def script_lines(self, exit_code: ExitCodeKind) -> Iterable[str]:
        factory = CHCFactory(self.function, self.tree_node_sort, self.lace_over_approx)

        yield "(set-logic HORN)"

        for lab in self.lace_over_approx.labels():
            name, return_sort, args_sorts = factory.predicate(lab)
            decl = decl_fun(name, return_sort, args_sorts)
            yield decl

        for lab in self.lace_over_approx.backbone_labels():
            chc = factory.chc_I(lab)
            assertion = assert_(chc)
            yield assertion

        for lab in self.lace_over_approx.start_labels():
            chc = factory.chc_II(lab)
            assertion = assert_(chc)
            yield assertion

        for step in self.lace_over_approx.steps():
            match step.dir:
                case Internal():
                    chc = factory.chc_III(step)
                case Down(_):
                    chc = factory.chc_IV(step)
                case Up():
                    chc = factory.chc_V(step)
            assertion = assert_(chc)
            yield assertion

        for lab in self.lace_over_approx.labels():
            if self._query_required(lab, exit_code):
                chc = factory.query(lab)
                assertion = assert_(chc)
                yield assertion

        yield "(check-sat)"
        yield "(exit)"

    def dump(
        self,
        file: TextIO,
        exit_code: ExitCodeKind,
    ):
        lines_iter = self.script_lines(exit_code)
        for line in lines_iter:
            file.write(line + "\n")

    def dump_to_file(
        self,
        file_path: str,
        exit_code: ExitCodeKind,
    ):
        with open(file_path, "w") as f:
            self.dump(f, exit_code)
