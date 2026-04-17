import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx.chc.core import ExitCodeKind
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label


def label_exit(label: Label, exit_codes: set[ExitCodeKind]) -> FNode:
    m = {
        ExitCodeKind.ERR: ERR(),
        ExitCodeKind.OOM: OOM(),
        ExitCodeKind.LABEL_OVERFLOW: LOF(),
        ExitCodeKind.CLEAN: Exit(),
    }
    exit_events = {m[code] for code in exit_codes}
    return smt.Bool(bool(label.frame.events.intersection(exit_events)))


def end_of_lace(label: Label) -> bool:
    return bool(label.frame.events.intersection({ERR(), LOF(), OOM(), Exit()}))
