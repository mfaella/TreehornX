"""TreehornX CLI."""

import csv
import json
import math
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Annotated, Callable, Literal, TypeAlias, cast

import typer
from humanfriendly import format_timespan

from treehornx import ir
from treehornx.analysis.constraints.sdta.SDTAContext import (
    SDTAContext,
    avl_ctx,
    avl_h_ctx,
    bst_ctx,
    bst_strict_ctx,
    not_avl_ctx,
    not_avl_h_ctx,
    not_avl_struct_ctx,
    not_bst_ctx,
    not_bst_strict_ctx,
    not_rb_black_height_ctx,
    not_rb_ctx,
    not_rb_red_ctx,
    not_rb_root_black_ctx,
    not_rb_struct_ctx,
    not_rb_struct_height_ctx,
    not_sll_sorted_ctx,
    not_sll_sorted_strict_ctx,
    rb_ctx,
    rb_struct_ctx,
    sll_sorted_ctx,
    sll_sorted_strict_ctx,
)
from treehornx.analysis.abstract_interpretation import MustConstantEngine, MustEqualityEngine
from treehornx.analysis.chc.system import CHCSystem
from treehornx.analysis.commons.ConstrTLab import ConstrTLab
from treehornx.analysis.constraints.ConstraintsBuilder import ConstraintsBuilder
from treehornx.analysis.constraints.errors import (
    memory_label_error,
    post_label_error,
    shape_edge_error,
    shape_label_error,
)
from treehornx.enum_models.enviroment import Env
from treehornx.enum_models.helpers import label_exit
from treehornx.enum_models.LabEngine import LabEngine
from treehornx.enum_models.labels import ExitCode, TLab
from treehornx.enum_models.TaintingEngine import TaintingEngine
from treehornx.analysis.chc.solvers import (
    CHCSolver,
    EldaricaSolver,
    GolemSolver,
    PortfolioSolver,
    SolverError,
    Status,
    Z3Solver,
)
from treehornx.symbolic_tree import NO_SPLIT, SymbolicTree, ordered
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

PreType: TypeAlias = Literal["bst", "bst_strict", "sll_sorted", "sll_sorted_strict", "avl", "avl_h", "rb", "rb_struct"]

PRE: dict[str, Callable[[], SDTAContext]] = {
    "bst": bst_ctx,
    "bst_strict": bst_strict_ctx,
    "sll_sorted": sll_sorted_ctx,
    "sll_sorted_strict": sll_sorted_strict_ctx,
    "avl": avl_ctx,
    "avl_h": avl_h_ctx,
    "rb": rb_ctx,
    "rb_struct": rb_struct_ctx,
}

PostType: TypeAlias = Literal[
    "bst",
    "bst_strict",
    "sll_sorted",
    "sll_sorted_strict",
    "avl",
    "avl_h",
    "rb",
    "rb_struct",
    "rb_red",
    "rb_black_height",
    "rb_root_black",
    "avl_struct",
    "rb_struct_height",
]

POST: dict[str, Callable[[], SDTAContext]] = {
    "bst": not_bst_ctx,
    "bst_strict": not_bst_strict_ctx,
    "sll_sorted": not_sll_sorted_ctx,
    "sll_sorted_strict": not_sll_sorted_strict_ctx,
    "avl": not_avl_ctx,
    "avl_h": not_avl_h_ctx,
    "rb": not_rb_ctx,
    "rb_struct": not_rb_struct_ctx,
    "rb_red": not_rb_red_ctx,
    "rb_black_height": not_rb_black_height_ctx,
    "rb_root_black": not_rb_root_black_ctx,
    "avl_struct": not_avl_struct_ctx,
    "rb_struct_height": not_rb_struct_height_ctx,
}
"""The negated automaton of each postcondition: it accepts the output trees that violate it."""

TREE_SHAPE = "TREE_SHAPE"
POST_CHECK = "POST"


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
    prune_elapsed_time: float = 0.0
    prune_pairs_checked: int = 0
    prune_pairs_removed: int = 0
    prune_pairs_unknown: int = 0
    phase_elapsed_time: dict[str, float] = field(default_factory=dict[str, float])
    """The time of the preprocessing phases of each check (`<check>`)."""
    phase_args_before: dict[str, int] = field(default_factory=dict[str, int])
    """The predicate arguments (sum over the labels) before each phase (`<check>_<phase>`)."""
    phase_args_after: dict[str, int] = field(default_factory=dict[str, int])
    phase_labels_count: dict[str, int] = field(default_factory=dict[str, int])
    phase_removed_count: dict[str, int] = field(default_factory=dict[str, int])
    """The labels removed by each phase (without a feasible derivation)."""
    systems_count: dict[str, int] = field(default_factory=dict[str, int])
    predicates_count: dict[str, int] = field(default_factory=dict[str, int])
    clauses_count: dict[str, int] = field(default_factory=dict[str, int])
    """The clauses of every system of the check, queries included."""
    queries_count: dict[str, int] = field(default_factory=dict[str, int])

    def start_check(self, check: str, systems: int) -> None:
        """Sets the number of systems of `check` and zeroes its times."""
        self.systems_count[check] = systems
        self.system_creation_elapsed_time[check] = 0.0
        self.smt2_dumping_elapsed_time[check] = 0.0
        self.check_sat_elapsed_time[check] = 0.0

    def add_counts(self, check: str, predicates: int, clauses: int, queries: int) -> None:
        self.predicates_count[check] = self.predicates_count.get(check, 0) + predicates
        self.clauses_count[check] = self.clauses_count.get(check, 0) + clauses
        self.queries_count[check] = self.queries_count.get(check, 0) + queries

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


TOP_DOWN_LEVEL = 2
"""The level of `--eq-prop`/`--const-prop` that also runs the top-down pass."""

EXIT_CODES: dict[str, ExitCode] = {"ERR": ExitCode.E, "OOM": ExitCode.M, "LABEL_OVERFLOW": ExitCode.O}
"""The memory checks: one system per exit status reached by the enumeration."""


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


def with_parent_field(function: ir.Function, name: str) -> ir.Function | None:
    """Declares the pointer field `name` the parent field: nil in every input node and not a child for the pre- and
    postcondition automata. The parent field gets the last pointer field id. None if it is not a pointer field."""
    pointer_fields = {f.name: f.id for f in function.node.pointer_fields}
    if name not in pointer_fields:
        error(
            f"--parent: struct {function.node.name} has no pointer field {name!r}, "
            f"its pointer fields are {', '.join(pointer_fields)}."
        )
        return None
    return with_parent_last(function, pointer_fields[name])


def with_parent_last(function: ir.Function, parent_id: int) -> ir.Function:
    """Renumbers the pointer fields so that the parent field has the last id. The other fields keep their order."""
    old_ids = [f.id for f in function.node.pointer_fields]
    order = [i for i in old_ids if i != parent_id] + [parent_id]
    new_id = {old: new for new, old in enumerate(order)}
    names = {f.id: f.name for f in function.node.pointer_fields}

    def cond(c: ir.Cond) -> ir.Cond:
        return replace(c, field=new_id[c.field]) if isinstance(c, ir.FieldIsNil) else c

    def stmt(s: ir.Stmt) -> ir.Stmt:
        if isinstance(s, (ir.LoadPtrField, ir.StoreNilField, ir.StorePtrField)):
            return replace(s, field=new_id[s.field])
        if isinstance(s, ir.AssignCond):
            return replace(s, cond=cond(s.cond))
        if isinstance(s, ir.IfGoto):
            return replace(s, cond=cond(s.cond))
        return s

    node = replace(
        function.node,
        pointer_fields=tuple(ir.PointerField(new_id[old], names[old]) for old in order),
        parent_field=new_id[parent_id],
    )
    return replace(function, node=node, statements=tuple(stmt(s) for s in function.statements))


def display_outcome(check: str, status: Status) -> None:
    match status:
        case Status.SAT:
            success(f"The function is correct with respect to {check}.")
        case Status.UNSAT:
            fail(f"The function is not correct with respect to {check}.")
        case _:
            warning(f"Unknown result for {check}.")


def system_counts(system: CHCSystem) -> tuple[int, int, int]:
    """The predicates used, the clauses (queries included) and the queries of `system`."""
    used = {app.predicate for clause in system.clauses for app in clause.applications()}
    return len(used), len(system.clauses), len(system.queries())


def smt2_counts(path: Path) -> tuple[int, int, int]:
    """The predicates, clauses (queries included) and queries of a HORN script written by `write_smt2`."""
    predicates = clauses = queries = 0
    with path.open() as f:
        for line in f:
            if line.startswith("(declare-fun"):
                predicates += 1
            elif line.startswith("(assert"):
                clauses += 1
                queries += line.rstrip().rstrip(")").endswith(" false")
    return predicates, clauses, queries


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
    post_ctx: SDTAContext | None = None,
) -> Stats:
    """Enumerates the labels, reports the exit statuses that are trivially unreachable and builds, dumps, prints
    and solves the CHC systems of the others. With `tree_shape` or `post_ctx`, memory safety is assumed: the memory
    systems are not built and the runs ending in ERR, OOM or label overflow are dropped; `tree_shape` builds the
    system checking that the output heap is a tree and `post_ctx` (a negated postcondition) the system checking that
    no output tree is accepted by it. Every system is on the inputs accepted by `pre_ctx`."""
    env = Env(function, len(function.node.pointer_fields), m, n)
    stats = Stats()

    lab_tree, stats.generation_elapsed_time = progress("Generating labels", lambda: LabEngine(env).finals())
    stats.labels_count = len(lab_tree.labels)
    stats.largest_label_length = max((len(label.lab) for label in lab_tree.labels), default=0)
    console.print(f"Label generation completed in {format_timespan(stats.generation_elapsed_time)}.")
    console.print(f"Generated {stats.labels_count} labels.\nLargest label length: {stats.largest_label_length}.")

    reached = {label_exit(label.lab, env) for label in lab_tree.labels}
    report_exit_codes(reached, stats)

    if not (smt2 or print_chc or solver):
        return stats

    def run(check: str, tree: SymbolicTree[TLab], builder: ConstraintsBuilder) -> None:
        run_check(function, check, tree, builder, smt2, print_chc, solver, timeout, flags, stats)

    if not (tree_shape or post_ctx):
        for name, code in EXIT_CODES.items():
            if code in reached:
                builder = ConstraintsBuilder(pre=pre_ctx, env=env, label_error=memory_label_error([code], env))
                run(name, lab_tree, builder)
        return stats

    info(
        "The tree-shape and postcondition checks assume memory safety: the memory systems are not built and the runs "
        "ending in ERR, OOM or LABEL_OVERFLOW are dropped."
    )
    if flags.prune_pairs:
        warning("--prune-pairs is not available in the current pipeline, it is ignored.")

    def taint() -> tuple[TaintingEngine, SymbolicTree[TLab]]:
        engine = TaintingEngine.from_lab(without_memory_errors(lab_tree, env), env)
        return engine, engine.finals()

    (engine, shape_tree), stats.taints_generation_elapsed_time = progress("Generating taints", taint)
    stats.tainted_labels_count = len(shape_tree.labels)
    console.print(
        f"Taint generation completed in {format_timespan(stats.taints_generation_elapsed_time)}: "
        f"{stats.tainted_labels_count} tainted labels."
    )

    if tree_shape:
        builder = ConstraintsBuilder(
            pre=pre_ctx,
            env=env,
            label_error=shape_label_error(engine),
            edge_error=shape_edge_error(engine),
        )
        run(TREE_SHAPE, shape_tree, builder)

    if post_ctx is not None:
        info("The postcondition check assumes that the function is memory safe and that the output heap is a tree.")
        builder = ConstraintsBuilder(
            pre=pre_ctx, post=post_ctx, env=env, label_error=post_label_error(engine, post_ctx)
        )
        run(POST_CHECK, shape_tree, builder)

    return stats


def report_exit_codes(reached: set[ExitCode], stats: Stats) -> None:
    """Reports each memory exit status as trivially safe when no final label reaches it."""
    for name, code in EXIT_CODES.items():
        stats.trivially_safe[name] = code not in reached
        if code in reached:
            fail(
                f"{name} is not trivially satisfiable, further analysis is needed to determine correctness "
                f"with respect to {name}."
            )
        else:
            success(f"{name} is trivially satisfiable, the function is correct with respect to {name}.")


def without_memory_errors(tree: SymbolicTree[TLab], env: Env) -> SymbolicTree[TLab]:
    """`tree` without the labels whose lace ends in ERR, OOM or label overflow, their edges, and what no longer
    composes a finite tree from a root."""
    codes = set(EXIT_CODES.values())

    def ok(label: TLab) -> bool:
        return label_exit(label.lab, env) not in codes

    kept = SymbolicTree(
        frozenset(e for e in tree.edges if ok(e.parent) and ok(e.child)),
        frozenset(filter(ok, tree.roots)),
        tree.arity,
        frozenset(filter(ok, tree.leaves)),
    )
    return kept.filter_edges(lambda _: True)


def args_count(tree: SymbolicTree[ConstrTLab]) -> int:
    """The predicate arguments, summed over the labels."""
    return sum(len(label.args()) for label in tree.labels)


def preprocess(
    check: str, tree: SymbolicTree[ConstrTLab], flags: FeatureFlags, stats: Stats
) -> SymbolicTree[ConstrTLab]:
    """The phases of `flags`: the equality must analysis (`--eq-prop`), then the constant propagation
    (`--const-prop`). Level 2 also runs the top-down pass."""
    phases: list[tuple[str, int, Callable[[SymbolicTree[ConstrTLab], bool], SymbolicTree[ConstrTLab]]]] = [
        ("eq", flags.eq_prop, lambda t, top_down: MustEqualityEngine(t, top_down).outputs()),
        ("const", flags.const_prop, lambda t, top_down: MustConstantEngine(t, top_down).outputs()),
    ]
    for name, level, phase in phases:
        if level == 0:
            continue
        key = f"{check}_{name}"
        stats.phase_args_before[key] = args_count(tree)
        before = tree
        tree, elapsed = progress(f"Running the {name} phase on {check}", lambda: phase(before, level >= TOP_DOWN_LEVEL))
        stats.phase_elapsed_time[key] = elapsed
        stats.phase_args_after[key] = args_count(tree)
        stats.phase_labels_count[key] = len(tree.labels)
        console.print(
            f"{name} phase on {check} in {format_timespan(elapsed)}: {stats.phase_args_before[key]} -> "
            f"{stats.phase_args_after[key]} predicate arguments."
        )
    return tree


def write_system(system: CHCSystem, path: Path | None, print_chc: bool, check: str) -> None:
    """Writes `system` to `path` (when given) and/or stdout."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            system.write(f)
    if print_chc:
        sys.stdout.write(f"; CHC system for {check}\n")
        if path is not None:
            with path.open() as f:
                shutil.copyfileobj(f, sys.stdout)
        else:
            system.write(sys.stdout)
        sys.stdout.flush()


def dump_system(system: CHCSystem, path: Path | None, print_chc: bool, check: str, name: str, stats: Stats) -> None:
    """Writes `system` to `path` and/or stdout (`write_system`) and records the time."""
    _, elapsed = progress(f"Writing the CHC system {name}", lambda: write_system(system, path, print_chc, check))
    stats.smt2_dumping_elapsed_time[check] += elapsed
    where = f": {path}" if path else " on stdout"
    console.print(f"CHC system {name} written in {format_timespan(elapsed)}{where}.")


def write_index(folder: Path, rows: list[list[object]], check: str) -> None:
    """The `index.csv` of the split systems of `check`: one row per system."""
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "index.csv").open("w", newline="") as index:
        writer = csv.writer(index)
        writer.writerow(["group", "file", "root_ids", "body", "pairs", "predicates", "clauses", "queries"])
        writer.writerows(rows)
    console.print(f"Index of the CHC systems for {check} written: {folder / 'index.csv'}.")


def solve_system(
    solver: CHCSolver, system: CHCSystem, deadline: float | None, check: str, name: str, stats: Stats
) -> Status | None:
    """Solves `system` in the time left before `deadline`; None when no time is left."""
    left = None
    if deadline is not None:
        left = math.ceil(deadline - time.monotonic())
        if left <= 0:
            return None
    status, elapsed = progress(f"Solving {name}", lambda: check_sat(solver, system, left))
    stats.check_sat_elapsed_time[check] += elapsed
    console.print(f"{name} solved in {format_timespan(elapsed)}: {status.value}.")
    return status


def run_check(
    function: ir.Function,
    check: str,
    tree: SymbolicTree[TLab],
    builder: ConstraintsBuilder,
    smt2: bool,
    print_chc: bool,
    solver: CHCSolver | None,
    timeout: int | None,
    flags: FeatureFlags,
    stats: Stats,
) -> None:
    """Lifts `tree` to `ConstrTLab` with `builder`, runs the phases, then builds, dumps, prints and solves the system
    of `check` (`CHCSystem.from_tree`).

    With `flags.split` > 0 the tree is split first (`SymbolicTree.split`) and each part gets its own system: `smt2`
    writes them into `<function>_<check>_split<N>/` with an `index.csv`, and the check is sat iff every system is sat
    (solving stops at the first unsat one; `timeout` is the budget of all the systems together)."""
    lifted = tree.map(lambda _, label: ConstrTLab(label, builder))
    lifted = preprocess(check, lifted, flags, stats)

    if flags.split == NO_SPLIT:
        parts = [lifted]
    else:
        parts, elapsed = progress(f"Splitting {check}", lambda: ordered(lifted.split(flags.split), lifted))
        console.print(f"{check} split in {format_timespan(elapsed)}: {len(lifted.roots)} roots, {len(parts)} systems.")
    root_index = {root: i for i, root in enumerate(lifted.roots)}
    folder = Path(f"{function.name}_{check}_split{flags.split}") if smt2 and flags.split != NO_SPLIT else None
    stats.start_check(check, len(parts))

    deadline = None if timeout is None else time.monotonic() + timeout
    result = Status.SAT
    rows: list[list[object]] = []
    for g, part in enumerate(parts):
        name = check if len(parts) == 1 and flags.split == NO_SPLIT else f"{check} {g + 1}/{len(parts)}"
        system, elapsed = progress(f"Creating the CHC system {name}", lambda: CHCSystem.from_tree(part))
        stats.system_creation_elapsed_time[check] += elapsed
        counts = system_counts(system)
        stats.add_counts(check, *counts)
        console.print(
            f"CHC system {name} created in {format_timespan(elapsed)}: {counts[0]} predicates, {counts[1]} clauses."
        )

        if smt2 or print_chc:
            path = None
            if smt2:
                file_name = f"{function.name}_{check}" + ("" if folder is None else f"_group{g:03d}") + ".smt2"
                path = Path(file_name) if folder is None else folder / file_name
            dump_system(system, path, print_chc, check, name, stats)
            if path is not None and folder is not None:
                roots = " ".join(map(str, sorted(root_index[root] for root in part.roots)))
                body = len(part.labels - part.roots)
                rows.append([g, path.name, roots, body, len(part.edges), *counts])

        if solver is None:
            continue
        status = solve_system(solver, system, deadline, check, name, stats)
        if status is None:
            result = Status.UNKNOWN
            break
        if status is Status.UNSAT:
            result = Status.UNSAT
            break
        if status is Status.UNKNOWN:
            result = Status.UNKNOWN

    if folder is not None:
        write_index(folder, rows, check)

    if solver is not None:
        stats.outcome[check] = result.value
        if len(parts) > 1:
            console.print(f"{check} solved in {format_timespan(stats.check_sat_elapsed_time[check])}: {result.value}.")
        display_outcome(check, result)


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
    parent: Annotated[
        str | None,
        typer.Option(
            "--parent",
            help="pointer field to the parent: nil in every input node, not a child for the --pre/--post automata",
        ),
    ] = None,
    produce_csv: Annotated[bool, typer.Option("--csv", help="dump the statistics in a CSV file")] = False,
    produce_json: Annotated[bool, typer.Option("--json", help="dump the statistics in a JSON file")] = False,
    tree_shape: Annotated[
        bool,
        typer.Option(
            "--tree-shape", help="check that the output heap is a tree (under --pre, if given), assuming memory safety"
        ),
    ] = False,
    post: Annotated[
        PostType | None,
        typer.Option(
            "--post",
            help="check that the output tree satisfies this postcondition (under --pre), assuming memory safety",
        ),
    ] = None,
    split: Annotated[
        int,
        typer.Option(
            "--split",
            min=0,
            max=3,
            help="split every system on the final labels before building it: 0 no split, 1 one system per maximal "
            "body (the roots whose body is included in another are collapsed into the smallest maximal one), "
            "2 one system per body (roots with the same derivations), 3 one system per root (query); "
            "--smt2 writes the systems into <function>_<check>_split<N>/",
        ),
    ] = 0,
    eq_prop_level: Annotated[
        int,
        typer.Option(
            "--eq-prop",
            min=0,
            max=2,
            help="equality must analysis: the symbols equal in every derivation of a label leave the predicate "
            "arguments but one: 0 off, 1 bottom-up, 2 bottom-up then top-down",
        ),
    ] = 0,
    const_prop_level: Annotated[
        int,
        typer.Option(
            "--const-prop",
            min=0,
            max=2,
            help="constant propagation: the symbols equal to a constant in every derivation of a label leave the "
            "predicate arguments, the labels without a feasible derivation are removed: 0 off, 1 bottom-up, "
            "2 bottom-up then top-down",
        ),
    ] = 0,
    prune_pairs: Annotated[
        bool,
        typer.Option(
            "--prune-pairs",
            help="with --tree-shape or --post, remove the Lab pairs whose data constraints are unsatisfiable "
            "(checked with yices-smt2, found in --solvers-dir or on PATH) before the tainting",
        ),
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
    if parent is not None:
        function = with_parent_field(function, parent)
        if function is None:
            raise typer.Exit(1)
        info(f"Parent field: {parent}, nil in every input node and not a child for the automata.")

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
        FeatureFlags(split, prune_pairs, eq_prop_level, const_prop_level),
        tree_shape,
        POST[post]() if post else None,
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
