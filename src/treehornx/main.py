"""TreehornX CLI."""

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated, Callable, Literal, TypeAlias, cast

import typer
from humanfriendly import format_timespan
from pychc.chc_system import CHCSystem
from pychc.solvers.chc_solver import CHCSolver
from pychc.solvers.eldarica import EldaricaSolver
from pychc.solvers.golem import GolemSolver
from pychc.solvers.witness import Status
from pychc.solvers.z3 import Z3CHCSolver

from treehornx import ir
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.clauses import query
from treehornx.chc.Lab.system import LabCHC, build_lab, to_system
from treehornx.chc.pre import PreRunner
from treehornx.chc.sdta.SDTAContext import (
    SDTAContext,
    avl_ctx,
    bst_ctx,
    bst_strict_ctx,
    sll_sorted_ctx,
    sll_sorted_strict_ctx,
)
from treehornx.enum_models.Lab import ERR, OOM, Lab
from treehornx.parser import SubsetError, parse_file
from treehornx.tui import console, critical, error, fail, info, progress, success, warning

app = typer.Typer(help="TreehornX CLI.")


@app.callback()
def callback() -> None:
    """TreehornX: formal verification of tree-manipulating programs."""


DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_ROOT = "root"

PreType: TypeAlias = Literal["bst", "bst_strict", "sll_sorted", "sll_sorted_strict", "avl"]

PRE: dict[str, Callable[[], SDTAContext]] = {
    "bst": bst_ctx,
    "bst_strict": bst_strict_ctx,
    "sll_sorted": sll_sorted_ctx,
    "sll_sorted_strict": sll_sorted_strict_ctx,
    "avl": avl_ctx,
}

EXIT_CODES = (ExitCodeKind.ERR, ExitCodeKind.OOM, ExitCodeKind.LABEL_OVERFLOW)


@dataclass
class Stats:
    generation_elapsed_time: float = 0.0
    labels_count: int = 0
    largest_label_length: int = 0
    lab_predicates: int = 0
    trivially_safe: dict[str, bool] = field(default_factory=dict[str, bool])
    system_creation_elapsed_time: dict[str, float] = field(default_factory=dict[str, float])
    smt2_dumping_elapsed_time: dict[str, float] = field(default_factory=dict[str, float])
    check_sat_elapsed_time: dict[str, float] = field(default_factory=dict[str, float])
    outcome: dict[str, str] = field(default_factory=dict[str, str])

    def rows(self) -> list[tuple[str, object]]:
        rows: list[tuple[str, object]] = []
        for name, value in asdict(self).items():
            if isinstance(value, dict):
                entries = cast(dict[str, object], value)
                rows.extend((f"{name}_{key}", v) for key, v in entries.items())
            else:
                rows.append((name, value))
        return rows


# ---------------------------------------------------------------------------
# verification steps
# ---------------------------------------------------------------------------


def label_exit(label: Lab, n: int) -> set[ExitCodeKind]:
    """Exit statuses the lace of a label ends with: ERR, OOM and overflowing frames are never followed."""
    statuses: set[ExitCodeKind] = set()
    if isinstance(label.frame.event, ERR):
        statuses.add(ExitCodeKind.ERR)
    if isinstance(label.frame.event, OOM):
        statuses.add(ExitCodeKind.OOM)
    if len(label) == n + 1:
        statuses.add(ExitCodeKind.LABEL_OVERFLOW)
    return statuses


def memory_system(
    function: ir.Function, lab: LabCHC, m: int, n: int, exit_code: ExitCodeKind, pre_ctx: SDTAContext | None
) -> CHCSystem:
    """Unsat iff some execution (on an input accepted by the precondition) ends with `exit_code`."""
    k = function.node.k
    if pre_ctx is None:
        error_labels = (label for label in lab.predicates if exit_code in label_exit(label, n))
        queries = [q for label in error_labels if (q := query(lab.sym, label)) is not None]
        return to_system(lab.predicate_symbols(), [*lab.clauses, *queries])
    runner = PreRunner(function, lab.pairs, pre_ctx, k, m, sym=lab.sym, n=n, exit_codes=frozenset({exit_code}))
    return to_system(
        [*lab.predicate_symbols(), *runner.predicates()],
        [*lab.clauses, *runner.clauses(), *runner.queries()],
    )


def make_solver(z3: bool, golem: bool, eldarica: bool, solvers_dir: Path | None) -> CHCSolver:
    if z3:
        return Z3CHCSolver(binary_path=solvers_dir)
    if eldarica:
        return EldaricaSolver(binary_path=solvers_dir)
    return GolemSolver(binary_path=solvers_dir)


def check_sat(solver: CHCSolver, system: CHCSystem, timeout: int | None) -> Status:
    solver.load_system(system)
    try:
        return solver.solve(timeout=timeout)
    except Exception as e:  # the solver gives up without a result
        warning(f"the solver did not return a result: {e}")
        return Status.UNKNOWN


def display_option_messages(
    function_name: str | None,
    root_name: str | None,
    n: int | None,
    m: int | None,
    c: int | None,
    partial_correctness: bool,
    check_sat: bool,
    interactive_check_sat: bool,
    z3: bool,
    golem: bool,
    eldarica: bool,
    parent: str | None,
    dependency_graphs: bool,
) -> None:
    if function_name is None:
        info("No function specified, verifying the function in the file.")
    if root_name is None:
        info(f"No root specified, using default value of '{DEFAULT_ROOT}'.")
    if n is None:
        info(f"No value specified for n, using default value of {DEFAULT_N}.")
    if m is None:
        info(f"No value specified for m, using default value of {DEFAULT_M}.")
    if c is not None or partial_correctness:
        critical("-c and --partial-correctness are not supported by the current encoding, they are ignored.")
    if check_sat and not any((z3, golem, eldarica)):
        info("Using golem by default.")
    if interactive_check_sat:
        critical("--interactive-check-sat not supported, it is ignored.")
    if len([solver for solver in (z3, golem, eldarica) if solver]) > 1:
        warning("Multiple solvers specified, using " + ("z3." if z3 else "eldarica."))
    if parent is not None:
        critical("--parent not supported: the parser does not accept parent pointers, it is ignored.")
    if dependency_graphs:
        critical("dependency graphs are not supported by the current encoding, they are ignored.")


def check_names(function: ir.Function, function_name: str | None, root_name: str) -> bool:
    if function_name is not None and function.name != function_name:
        error(f"Function {function_name} not found, the file defines {function.name}.")
        return False
    if function.root.name != root_name:
        error(
            f"Root variable {root_name} not found, the root of {function.name} is its parameter {function.root.name}."
        )
        return False
    return True


def display_outcome(check: str, status: Status) -> None:
    match status:
        case Status.SAT:
            success(f"The function is correct with respect to {check}.")
        case Status.UNSAT:
            fail(f"The function is not correct with respect to {check}.")
        case _:
            warning(f"Unknown result for {check}.")


def verify(
    function: ir.Function,
    n: int,
    m: int,
    pre_ctx: SDTAContext | None,
    smt2: bool,
    solver: CHCSolver | None,
    timeout: int | None,
) -> Stats:
    """Enumerates the labels, reports the exit statuses that are trivially unreachable and builds, dumps and
    solves the CHC systems of the others."""
    k = function.node.k
    stats = Stats()

    lab, stats.generation_elapsed_time = progress("Generating labels", lambda: build_lab(function, k, m, n))
    final_labels, _ = lab.engine.finals()
    stats.labels_count = len(final_labels)
    stats.largest_label_length = max((len(label) for label in final_labels), default=0)
    stats.lab_predicates = len(lab.predicates)
    console.print(f"Label generation completed in {format_timespan(stats.generation_elapsed_time)}.")
    console.print(f"Generated {stats.labels_count} labels.\nLargest label length: {stats.largest_label_length}.")

    reached = set[ExitCodeKind]().union(*(label_exit(label, n) for label in lab.predicates))
    for exit_code in EXIT_CODES:
        stats.trivially_safe[exit_code.name] = exit_code not in reached
        if exit_code in reached:
            fail(
                f"{exit_code.name} is not trivially satisfiable, further analysis is needed to determine correctness "
                f"with respect to {exit_code.name}."
            )
        else:
            success(
                f"{exit_code.name} is trivially satisfiable, the function is correct with respect to {exit_code.name}."
            )

    if not (smt2 or solver):
        return stats

    checks: list[tuple[str, Callable[[], CHCSystem]]] = [
        (code.name, lambda code=code: memory_system(function, lab, m, n, code, pre_ctx))
        for code in EXIT_CODES
        if code in reached
    ]

    for check, make_system in checks:
        system, elapsed = progress(f"Creating the CHC system for {check}", make_system)
        stats.system_creation_elapsed_time[check] = elapsed
        console.print(f"CHC system for {check} created in {format_timespan(elapsed)}.")

        if smt2:
            file_path = Path(f"{function.name}_{check}.smt2")
            _, elapsed = progress(f"Creating SMT2 script for {check}", lambda: system.serialize(file_path))
            stats.smt2_dumping_elapsed_time[check] = elapsed
            console.print(f"SMT2 script for {check} created in {format_timespan(elapsed)}: {file_path}.")

        if solver is not None:
            status, elapsed = progress(f"Solving {check}", lambda: check_sat(solver, system, timeout))
            stats.check_sat_elapsed_time[check] = elapsed
            stats.outcome[check] = status.value
            console.print(f"{check} solved in {format_timespan(elapsed)}: {status.value}.")
            display_outcome(check, status)

    return stats


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


@app.command("verify")
def verify_cmd(
    input_file: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    function_name: Annotated[str | None, typer.Option("--function", "-f")] = None,
    root_name: Annotated[str | None, typer.Option("--root", "-r")] = None,
    n: Annotated[int | None, typer.Option("-n", help="maximum number of frames per label")] = None,
    m: Annotated[int | None, typer.Option("-m", help="maximum number of nodes allocated by the function")] = None,
    c: Annotated[int | None, typer.Option("-c", help="not supported")] = None,
    partial_correctness: Annotated[bool, typer.Option("--partial-correctness", help="not supported")] = False,
    smt2: Annotated[bool, typer.Option("--smt2", help="dump the CHC systems as SMT-LIB2 scripts")] = False,
    check_sat_flag: Annotated[bool, typer.Option("--check-sat", help="solve the CHC systems")] = False,
    interactive_check_sat: Annotated[bool, typer.Option("--interactive-check-sat", help="not supported")] = False,
    z3: Annotated[bool, typer.Option("--z3")] = False,
    golem: Annotated[bool, typer.Option("--golem")] = False,
    eldarica: Annotated[bool, typer.Option("--eldarica")] = False,
    solvers_dir: Annotated[
        Path | None, typer.Option("--solvers-dir", help="directory of the solver binaries, PATH by default")
    ] = None,
    timeout: Annotated[int | None, typer.Option("--timeout", help="solver timeout in seconds")] = None,
    full_dep_graph: Annotated[bool, typer.Option("--fdg", "--full-dep-graph", help="not supported")] = False,
    compressed_dep_graph: Annotated[
        bool, typer.Option("--cdg", "--compressed-dep-graph", help="not supported")
    ] = False,
    internal_dependency_graph: Annotated[
        bool, typer.Option("--idg", "--internal-dep-graph", help="not supported")
    ] = False,
    pre: Annotated[PreType | None, typer.Option("--pre")] = None,
    parent: Annotated[str | None, typer.Option("--parent", help="not supported")] = None,
    produce_csv: Annotated[bool, typer.Option("--csv", help="dump the statistics in a CSV file")] = False,
    produce_json: Annotated[bool, typer.Option("--json", help="dump the statistics in a JSON file")] = False,
) -> None:
    display_option_messages(
        function_name,
        root_name,
        n,
        m,
        c,
        partial_correctness,
        check_sat_flag,
        interactive_check_sat,
        z3,
        golem,
        eldarica,
        parent,
        full_dep_graph or compressed_dep_graph or internal_dependency_graph,
    )
    root_name = root_name or DEFAULT_ROOT

    try:
        function = parse_file(str(input_file))
    except (SubsetError, OSError) as e:
        error(f"Error parsing {input_file}: {e}")
        raise typer.Exit(1) from e
    if not check_names(function, function_name, root_name):
        raise typer.Exit(1)

    solver = make_solver(z3, golem, eldarica, solvers_dir) if check_sat_flag else None
    stats = verify(
        function,
        n or DEFAULT_N,
        m or DEFAULT_M,
        PRE[pre]() if pre else None,
        smt2,
        solver,
        timeout,
    )
    dump_stats(function, stats, produce_csv, produce_json)


def dump_stats(function: ir.Function, stats: Stats, produce_csv: bool, produce_json: bool) -> None:
    if produce_csv:
        file_path = Path(f"{function.name}_stats.csv")
        with file_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Metric", "Value"])
            writer.writerows(stats.rows())
        info(f"Statistics written to {file_path}.")
    if produce_json:
        file_path = Path(f"{function.name}_stats.json")
        file_path.write_text(json.dumps(asdict(stats), indent=2))
        info(f"Statistics written to {file_path}.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
