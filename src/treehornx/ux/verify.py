from pathlib import Path
from typing import Iterable

from humanfriendly import format_timespan
from rich.console import Console

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.pre.PreContext import PreContext
from treehornx.enum_labels import KnittedTrees, generate_labels
from treehornx.enum_labels.core.Event import ERR, LOF, OOM
from treehornx.ir._internal.sorts.natives import Pointer
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.ir.sorts import Struct
from treehornx.ux.stats import stats
from treehornx.ux.tui import progress
from treehornx.ux.utils import take_time


def compute_trivially_sat(lace_over_approx: KnittedTrees) -> dict[ExitCodeKind, bool]:
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
) -> KnittedTrees:
    def display_label_generation_progress(console: Console) -> KnittedTrees:
        lace_over_approx, elapsed_time = take_time(lambda: generate_labels(function, root, m, n, c))
        console.print(f"Label generation completed in {format_timespan(elapsed_time)}.")
        stats.generation_elapsed_time = elapsed_time
        return lace_over_approx

    trees = progress("Generating labels", display_label_generation_progress)
    labels_count = len(list(trees.labels()))
    largest_label_lenght = max(len(lab) for lab in trees.labels()) if labels_count > 0 else 0
    Console().print(f"Generated {labels_count} labels.\nLargest label length: {largest_label_lenght}.")
    stats.labels_count = labels_count
    stats.largest_label_length = largest_label_lenght
    return trees


def handle_smt2_scripts_creation(
    function: Function,
    root: Var,
    lace_over_approx: KnittedTrees,
    exit_codes: Iterable[ExitCodeKind],
    pre_ctx: PreContext | None = None,
    post: bool = False,
    output_dir: Path | None = None,
):
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct), (
        "Root variable must be a pointer to a struct."
    )
    tree_node_sort = root.sort.pointee
    if post:
        enable_post_is_tree = True
        root_name = root.name
    else:
        enable_post_is_tree = False
        root_name = None
    system_factory = CHCSystemFactory(
        function, tree_node_sort, lace_over_approx, pre_ctx, enable_post_is_tree, root_name
    )
    maybe_exit_codes = list(exit_codes) or [None]
    for exit_code in maybe_exit_codes:

        def display_smt2_script_creation_progress(console: Console) -> float:
            file_path = Path(f"{function.name}{f'_{exit_code.name}' if exit_code else ''}.smt2")
            if output_dir is not None:
                file_path = output_dir / file_path

            def serialize():
                system = system_factory.make_system(exit_code)
                system.serialize(file_path)

            _, elapsed_time = take_time(serialize)
            console.print(
                f"SMT2 script{f' for {exit_code.name}' if exit_code else ''} created in {format_timespan(elapsed_time)}."
            )
            return elapsed_time

        elapsed_time = progress(
            f"Creating SMT2 script{f' for {exit_code.name}' if exit_code else ''}",
            display_smt2_script_creation_progress,
        )
        match exit_code:
            case None:
                pass
            case ExitCodeKind.ERR:
                stats.smt2_err_scripts_dumping_elpased_time = elapsed_time
            case ExitCodeKind.OOM:
                stats.smt2_oom_scripts_dumping_elpased_time = elapsed_time
            case ExitCodeKind.LABEL_OVERFLOW:
                stats.smt2_lof_scripts_dumping_elpased_time = elapsed_time
            case ExitCodeKind.CLEAN:
                pass
