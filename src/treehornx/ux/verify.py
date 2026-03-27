from typing import Iterable

from humanfriendly import format_timespan
from rich.console import Console

from treehornx.chc import ExitCodeKind, SMT2ScriptPrinter
from treehornx.enum_labels import LaceOverApproximation, generate_labels
from treehornx.enum_labels.core.Event import ERR, LOF, OOM
from treehornx.ir._internal.sorts.natives import Pointer
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.ir.sorts import Struct
from treehornx.ux.tui import progress
from treehornx.ux.utils import take_time


def compute_trivially_sat(lace_over_approx: LaceOverApproximation) -> dict[ExitCodeKind, bool]:
    trivially_sat: dict[ExitCodeKind, bool] = {
        ExitCodeKind.ERR: True,
        ExitCodeKind.LABEL_OVERFLOW: True,
        ExitCodeKind.OOM: True,
    }
    for lab in lace_over_approx.labels():
        if ERR() in lab.frame.events:
            trivially_sat[ExitCodeKind.ERR] = False
        elif LOF() in lab.frame.events:
            trivially_sat[ExitCodeKind.LABEL_OVERFLOW] = False
        elif OOM() in lab.frame.events:
            trivially_sat[ExitCodeKind.OOM] = False
    return trivially_sat


def handle_label_generation(
    function: Function,
    root: Var,
    n: int,
    m: int,
    c: int | None,
) -> LaceOverApproximation:
    def display_label_generation_progress(console: Console) -> LaceOverApproximation:
        lace_over_approx, elapsed_time = take_time(lambda: generate_labels(function, root, m, n, c))
        console.print(f"Label generation completed in {format_timespan(elapsed_time)}.")
        return lace_over_approx

    lace_over_approx = progress("Generating labels", display_label_generation_progress)
    return lace_over_approx


def handle_smt2_scripts_creation(
    function: Function,
    root: Var,
    lace_over_approx: LaceOverApproximation,
    exit_codes: Iterable[ExitCodeKind],
) -> None:
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct), (
        "Root variable must be a pointer to a struct."
    )
    tree_node_sort = root.sort.pointee
    script_builder = SMT2ScriptPrinter(function, tree_node_sort, lace_over_approx)
    for exit_code in exit_codes:

        def display_smt2_script_creation_progress(console: Console) -> None:
            with open(f"{function.name}_{exit_code.name}.smt2", "w") as f:
                _, elapsed_time = take_time(lambda: script_builder.dump(f, exit_code))
            console.print(f"SMT2 script for {exit_code.name} created in {format_timespan(elapsed_time)}.")

        progress(f"Creating SMT2 script for {exit_code.name}", display_smt2_script_creation_progress)
