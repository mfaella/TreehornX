"""TreehornX CLI."""

import csv
import itertools
import json
import shutil
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Annotated, Callable, Iterable, Literal, TypeAlias, cast

import typer
from humanfriendly import format_timespan

from treehornx import ir
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.system import LabCHC, build_lab, to_system, write_smt2
from treehornx.chc.pre import PreRunner, label_exit
from treehornx.chc.sdta.SDTAContext import (
    SDTAContext,
    avl_ctx,
    bst_ctx,
    bst_strict_ctx,
    rb_ctx,
    sll_sorted_ctx,
    sll_sorted_strict_ctx,
    true_ctx,
)
from treehornx.chc.smt.sexpr import CHCSystem, Clause, Predicate
from treehornx.chc.solvers import (
    CHCSolver,
    EldaricaSolver,
    GolemSolver,
    PortfolioSolver,
    SolverError,
    Status,
    Z3Solver,
)
from treehornx.chc.TreeShape import tree_shape_clauses, tree_shape_from_lab
from treehornx.feature_flags import FeatureFlags
from treehornx.parser import SubsetError, parse_file
from treehornx.tui import console, critical, error, fail, info, progress, success, warning


app = typer.Typer(help="TreehornX CLI.")


@app.callback()
def callback() -> None:
    """TreehornX: formal verification of tree-manipulating programs."""


DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_ROOT = "root"

PreType: TypeAlias = Literal["bst", "bst_strict", "sll_sorted", "sll_sorted_strict", "avl", "rb"]

PRE: dict[str, Callable[[], SDTAContext]] = {
    "bst": bst_ctx,
    "bst_strict": bst_strict_ctx,
    "sll_sorted": sll_sorted_ctx,
    "sll_sorted_strict": sll_sorted_strict_ctx,
    "avl": avl_ctx,
    "rb": rb_ctx,
}

EXIT_CODES = (ExitCodeKind.ERR, ExitCodeKind.OOM, ExitCodeKind.LABEL_OVERFLOW)
TREE_SHAPE = "TREE_SHAPE"


@dataclass
class Stats:
    generation_elapsed_time: float = 0.0
    labels_count: int = 0
    taints_generation_elapsed_time: float = 0.0
    tainted_labels_count: int = 0
    largest_label_length: int = 0
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


def memory_clauses(
    function: ir.Function, lab: LabCHC, m: int, n: int, exit_code: ExitCodeKind, pre_ctx: SDTAContext | None
) -> tuple[list[Predicate], Iterable[Clause]]:
    """Predicates and (lazily generated) clauses of a system that is unsat iff some execution (on an input accepted
    by the precondition) ends with `exit_code`. Without a precondition every input is accepted."""
    k = function.node.k
    runner = PreRunner(
        function, lab.pairs, pre_ctx or true_ctx(), k, m, sym=lab.sym, n=n, exit_codes=frozenset({exit_code})
    )
    return runner.predicates(), itertools.chain(runner.clauses(), runner.queries())


Clauses: TypeAlias = Callable[[], tuple[list[Predicate], Iterable[Clause]]]
"""Builds the predicates and the (lazily generated) clauses of a check's system."""


def dump_system(
    function: ir.Function, check: str, clauses: Clauses, smt2: bool, print_chc: bool, flags: FeatureFlags
) -> Path | None:
    """Streams the system to `<function>_<check>.smt2` and/or stdout without building a `CHCSystem`."""
    _, body = clauses()
    if not smt2:
        sys.stdout.write(f"; CHC system for {check}\n")
        write_smt2(body, sys.stdout, flags.clean_clause)
        sys.stdout.flush()
        return None
    file_path = Path(f"{function.name}_{check}.smt2")
    with file_path.open("w") as f:
        write_smt2(body, f, flags.clean_clause)
    if print_chc:
        sys.stdout.write(f"; CHC system for {check}\n")
        with file_path.open() as f:
            shutil.copyfileobj(f, sys.stdout)
        sys.stdout.flush()
    return file_path


SOLVERS: dict[str, Callable[[Path | None], CHCSolver]] = {
    "z3": Z3Solver,
    "eldarica": EldaricaSolver,
    "golem": GolemSolver,
    "portfolio": PortfolioSolver,
}


def make_solver(solvers: list[str], solvers_dir: Path | None) -> CHCSolver:
    """The first of the chosen solvers, z3 when none is chosen."""
    return SOLVERS[solvers[0] if solvers else "z3"](solvers_dir)


def check_sat(solver: CHCSolver, system: CHCSystem, timeout: int | None) -> Status:
    try:
        return solver.solve(system, timeout)
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
    solvers: list[str],
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
    if check_sat and not solvers:
        info("Using z3 by default.")
    if interactive_check_sat:
        critical("--interactive-check-sat not supported, it is ignored.")
    if len(solvers) > 1:
        warning(f"Multiple solvers specified, using {solvers[0]}.")
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


def with_nil_fields(function: ir.Function, names: list[str]) -> ir.Function | None:
    """Declares the pointer fields `names` nil in every input node, None if one of them is not a pointer field."""
    pointer_fields = {f.name: f.id for f in function.node.pointer_fields}
    unknown = [name for name in names if name not in pointer_fields]
    if unknown:
        error(
            f"--nil-field: struct {function.node.name} has no pointer field {', '.join(map(repr, unknown))}, "
            f"its pointer fields are {', '.join(pointer_fields)}."
        )
        return None
    nil_fields = function.node.nil_fields | {pointer_fields[name] for name in names}
    return replace(function, node=replace(function.node, nil_fields=nil_fields))


def display_outcome(check: str, status: Status) -> None:
    match status:
        case Status.SAT:
            success(f"The function is correct with respect to {check}.")
        case Status.UNSAT:
            fail(f"The function is not correct with respect to {check}.")
        case _:
            warning(f"Unknown result for {check}.")


def run_check(
    function: ir.Function,
    check: str,
    clauses: Clauses,
    smt2: bool,
    print_chc: bool,
    solver: CHCSolver | None,
    timeout: int | None,
    flags: FeatureFlags,
    stats: Stats,
) -> None:
    """Dumps, prints and solves the system of `check`."""
    if smt2 or print_chc:
        file_path, elapsed = progress(
            f"Writing the CHC system for {check}",
            lambda: dump_system(function, check, clauses, smt2, print_chc, flags),
        )
        stats.smt2_dumping_elapsed_time[check] = elapsed
        where = f": {file_path}" if file_path else " on stdout"
        console.print(f"CHC system for {check} written in {format_timespan(elapsed)}{where}.")

    if solver is not None:
        system, elapsed = progress(
            f"Creating the CHC system for {check}", lambda: to_system(*clauses(), flags.clean_clause)
        )
        stats.system_creation_elapsed_time[check] = elapsed
        console.print(f"CHC system for {check} created in {format_timespan(elapsed)}.")
        status, elapsed = progress(f"Solving {check}", lambda: check_sat(solver, system, timeout))
        stats.check_sat_elapsed_time[check] = elapsed
        stats.outcome[check] = status.value
        console.print(f"{check} solved in {format_timespan(elapsed)}: {status.value}.")
        display_outcome(check, status)


def verify(
    function: ir.Function,
    n: int,
    m: int,
    pre_ctx: SDTAContext | None,
    smt2: bool,
    print_chc: bool,
    solver: CHCSolver | None,
    timeout: int | None,
    flags: FeatureFlags,
    tree_shape: bool = False,
) -> Stats:
    """Enumerates the labels, reports the exit statuses that are trivially unreachable and builds, dumps, prints
    and solves the CHC systems of the others. With `tree_shape`, also the system checking that the output heap
    is a tree (on the inputs accepted by the precondition, as the others)."""
    k = function.node.k
    stats = Stats()

    lab, stats.generation_elapsed_time = progress("Generating labels", lambda: build_lab(function, k, m, n))
    stats.labels_count = len(lab.labels)
    stats.largest_label_length = max((len(label) for label in lab.labels), default=0)
    console.print(f"Label generation completed in {format_timespan(stats.generation_elapsed_time)}.")
    console.print(f"Generated {stats.labels_count} labels.\nLargest label length: {stats.largest_label_length}.")

    reached = set[ExitCodeKind]().union(*(label_exit(label, n) for label in lab.labels))
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

    if not (smt2 or print_chc or solver):
        return stats

    for code in (code for code in EXIT_CODES if code in reached):
        run_check(
            function,
            code.name,
            lambda code=code: memory_clauses(function, lab, m, n, code, pre_ctx),
            smt2,
            print_chc,
            solver,
            timeout,
            flags,
            stats,
        )

    if tree_shape:
        info("The tree-shape check assumes that the function is memory safe (ERR, OOM and LABEL_OVERFLOW).")
        shape, stats.taints_generation_elapsed_time = progress("Generating taints", lambda: tree_shape_from_lab(lab))
        stats.tainted_labels_count = len(shape.labels)
        console.print(
            f"Taint generation completed in {format_timespan(stats.taints_generation_elapsed_time)}: "
            f"{stats.tainted_labels_count} tainted labels."
        )
        run_check(
            function,
            TREE_SHAPE,
            lambda: tree_shape_clauses(function, shape, m, n, pre_ctx),
            smt2,
            print_chc,
            solver,
            timeout,
            flags,
            stats,
        )

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
    print_chc: Annotated[
        bool, typer.Option("--print-chc", help="print the CHC systems on stdout, every other message goes to stderr")
    ] = False,
    check_sat_flag: Annotated[bool, typer.Option("--check-sat", help="solve the CHC systems")] = False,
    interactive_check_sat: Annotated[bool, typer.Option("--interactive-check-sat", help="not supported")] = False,
    z3: Annotated[bool, typer.Option("--z3")] = False,
    eldarica: Annotated[bool, typer.Option("--eldarica")] = False,
    golem: Annotated[bool, typer.Option("--golem")] = False,
    portfolio: Annotated[
        bool, typer.Option("--portfolio", help="run golem, z3 and eldarica at the same time, the first answer wins")
    ] = False,
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
    nil_fields: Annotated[
        list[str] | None,
        typer.Option("--nil-field", help="pointer field that is nil in every input node (repeatable)"),
    ] = None,
    produce_csv: Annotated[bool, typer.Option("--csv", help="dump the statistics in a CSV file")] = False,
    produce_json: Annotated[bool, typer.Option("--json", help="dump the statistics in a JSON file")] = False,
    clean_clause: Annotated[
        bool, typer.Option("--clean-clause", help="merge the variables equated in a clause body")
    ] = False,
    tree_shape: Annotated[
        bool,
        typer.Option("--tree-shape", help="also check that the output heap is a tree (under --pre, if given)"),
    ] = False,
) -> None:
    solver_flags = {"z3": z3, "eldarica": eldarica, "golem": golem, "portfolio": portfolio}
    solvers = [name for name, chosen in solver_flags.items() if chosen]
    display_option_messages(
        function_name,
        root_name,
        n,
        m,
        c,
        partial_correctness,
        check_sat_flag,
        interactive_check_sat,
        solvers,
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
    if nil_fields:
        function = with_nil_fields(function, nil_fields)
        if function is None:
            raise typer.Exit(1)
        info(f"Pointer fields nil in every input node: {', '.join(nil_fields)}.")

    try:
        solver = make_solver(solvers, solvers_dir) if check_sat_flag else None
    except SolverError as e:
        error(str(e))
        raise typer.Exit(1) from e
    stats = verify(
        function,
        n or DEFAULT_N,
        m or DEFAULT_M,
        PRE[pre]() if pre else None,
        smt2,
        print_chc,
        solver,
        timeout,
        FeatureFlags(clean_clause),
        tree_shape,
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
