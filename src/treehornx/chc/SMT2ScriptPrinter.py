from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from pychc.chc_system import CHCSystem
from pysmt import logics

from treehornx.chc._internal.LabFactory import LabFactory
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

    def dump(
        self,
        file_path: str | Path,
        exit_code: ExitCodeKind,
    ):
        factory = LabFactory(self.function, self.tree_node_sort, self.lace_over_approx)

        H = CHCSystem(logic=logics.AUTO)  # noqa: N806

        for lab in self.lace_over_approx.labels():
            predicate = factory.predicate(lab)
            H.add_predicate(predicate)

        for lab in self.lace_over_approx.backbone_labels():
            chc = factory.chc_I(lab)
            H.add_clause(chc)

        for lab in self.lace_over_approx.start_labels():
            chc = factory.chc_II(lab)
            H.add_clause(chc)

        for step in self.lace_over_approx.steps():
            match step.dir:
                case Internal():
                    chc = factory.chc_III(step)
                case Down(_):
                    chc = factory.chc_IV(step)
                case Up():
                    chc = factory.chc_V(step)
            H.add_clause(chc)

        for lab in self.lace_over_approx.labels():
            if self._query_required(lab, exit_code):
                chc = factory.query(lab)
                H.add_clause(chc)

        H.serialize(Path(file_path))
