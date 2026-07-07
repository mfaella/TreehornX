from collections import defaultdict
import csv
from enum import Enum
import time

from dataclasses import dataclass, field
from pathlib import Path

from pychc.solvers.chc_solver import CHCSolver, Status # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.golem import GolemSolver # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.z3 import Z3CHCSolver # pyright: ignore[reportMissingTypeStubs]
from pysmt.shortcuts import reset_env

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.contracts.Contract import Contract, read_only_contract
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.SDTAContext import (
    SDTAContext,
    avl_ctx,
    avl_wbf_ctx,
    bst_ctx,
    bst_strict_ctx,
    not_avl_ctx,
    not_avl_wbf_ctx,
    not_bst_ctx,
    not_bst_strict_ctx,
    not_sll_sorted_ctx,
    not_sll_sorted_strict_ctx,
    sll_sorted_strict_ctx,
)
from treehornx.chc.post.tainting import Tainter
from treehornx.chc.post.tainting.core import TaintedLabel
from treehornx.enum_labels import generate_labels
from treehornx.ir.sorts import Pointer, Struct
from treehornx.parser.CParser import CParser

C_FILES_DIR = Path(__file__).parent / "c_files"

DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_C = 32

def default_chc_solver() -> CHCSolver:
    path = Path(__file__).parent / "solvers" / "linux" / "x86-64"
    return GolemSolver(binary_path=path)
    # return Z3CHCSolver(binary_path=path)

class VerificationOutcome(Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"

@dataclass
class BenchmarkConfig:
    file_name: Path
    n: int = DEFAULT_N
    m: int = DEFAULT_M
    c: int = DEFAULT_C
    pre_ctx: SDTAContext|None = None
    post_ctx: bool | SDTAContext | Contract[TaintedLabel] = False
    parent: str | None = None
    solver: CHCSolver = field(default_factory = default_chc_solver)

@dataclass
class BenchmarkResult:
    trivially_safe_for: defaultdict[str, bool|None] = field(default_factory=lambda: defaultdict(lambda: None))
    labels_generation_elapsed_time: float | None = None
    labels_generation_timed_out: bool = False
    solving_elapsed_time_for: defaultdict[str, float|None] = field(default_factory=lambda: defaultdict(lambda: None))
    solving_timed_out_for: defaultdict[str, bool|None] = field(default_factory=lambda: defaultdict(lambda: None))
    system_creation_elapsed_time_for: defaultdict[str, float|None] = field(default_factory=lambda: defaultdict(lambda: None))
    system_creation_timed_out_for: defaultdict[str, bool|None] = field(default_factory=lambda: defaultdict(lambda: None))
    outcome_for: defaultdict[str, VerificationOutcome|None] = field(default_factory=lambda: defaultdict(lambda: None))
    number_of_chcs: int | None = None
    longest_label_len: int | None = None
    number_of_tainted_labels: int | None = None

def status_to_outcome(status: Status) -> VerificationOutcome:
    if status == Status.SAT:
        return VerificationOutcome.SAFE
    elif status == Status.UNSAT:
        return VerificationOutcome.UNSAFE
    else:
        return VerificationOutcome.UNKNOWN

def trivially_safe_for(system_factory: CHCSystemFactory, key: str) -> bool:
    match key:
        case "err":
            return system_factory.trivially_safe_for_err
        case "oom":
            return system_factory.trivially_safe_for_oom
        case "lof":
            return system_factory.trivially_safe_for_lof
        case "post_is_tree":
            # `trivially_safe_for_post_is_tree` only reflects the tree-shape (T)
            # check. When a full post-condition context is provided, the
            # post-condition property (S) must always be solved, even if the
            # tree shape is trivially preserved.
            if isinstance(system_factory.post_ctx, SDTAContext):
                return False
            return system_factory.trivially_safe_for_post_is_tree
        case _:
            raise ValueError(f"Unknown key: {key}")

def key_to_exit_code_kind(key: str) -> ExitCodeKind|None:
    match key:
        case "err":
            return ExitCodeKind.ERR
        case "oom":
            return ExitCodeKind.OOM
        case "lof":
            return ExitCodeKind.LABEL_OVERFLOW
        case "post_is_tree":
            return None
        case _:
            raise ValueError(f"Unknown key: {key}")

def solve_for_key(config: BenchmarkConfig, system_factory: CHCSystemFactory, key: str, result: BenchmarkResult, timeout: int):
    if not trivially_safe_for(system_factory, key):
        result.trivially_safe_for[key] = False
        exit_code_kind = key_to_exit_code_kind(key)
        start = time.perf_counter()
        system = system_factory.make_system(exit_code_kind)
        end = time.perf_counter()
        result.system_creation_timed_out_for[key] = False
        result.system_creation_elapsed_time_for[key] = end - start


        def load_and_solve():
            start = time.perf_counter()
            config.solver.load_system(system)
            input_file = config.solver.get_input_file()
            end = time.perf_counter()
            remaining_timeout = timeout - int(end - start)
            return config.solver.run(input_file, timeout=remaining_timeout)
        start = time.perf_counter()
        status = load_and_solve()
        end = time.perf_counter()
        result.outcome_for[key] = status_to_outcome(status)
        result.solving_timed_out_for[key] = False
        result.solving_elapsed_time_for[key] = end - start
        return len(list(system.get_clauses()))

    else:
        result.outcome_for[key] = VerificationOutcome.SAFE
        result.trivially_safe_for[key] = True
        return 0

def run_benchmark(config: BenchmarkConfig, timeout: int) -> BenchmarkResult:
    parser = CParser()
    function = next(iter(parser.parse_file(str(config.file_name))))
    root = next(var for var in function.vars if var.name == "root_0")
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct)
    result = BenchmarkResult()
    start_time = time.perf_counter()
    trees = generate_labels(function, root, config.m, config.n, config.c, parent_name=config.parent)
    end_time = time.perf_counter()
    result.labels_generation_timed_out = False
    result.labels_generation_elapsed_time = end_time - start_time
    system_factory = CHCSystemFactory(
        function,
        root.sort.pointee,
        trees,
        config.pre_ctx,
        config.post_ctx,
        root.name
    )

    chc_num = solve_for_key(config, system_factory, "err", result, timeout)

    chc_num = max(solve_for_key(config, system_factory, "oom", result, timeout), chc_num)

    chc_num = max(solve_for_key(config, system_factory, "lof", result, timeout), chc_num)

    if (
        system_factory.trivially_safe_for_err and
        system_factory.trivially_safe_for_oom and
        system_factory.trivially_safe_for_lof and
        config.post_ctx
    ):
        chc_num = max(solve_for_key(config, system_factory, "post_is_tree", result, timeout), chc_num)

    result.number_of_chcs = chc_num
    result.longest_label_len = max(len(label) for label in trees.labels())
    if config.post_ctx:
        result.trivially_safe_for["post_is_tree"] = system_factory.trivially_safe_for_post_is_tree
        result.number_of_tainted_labels = len(Tainter(root.name, trees).taint()[1]) if config.post_ctx else None

    return result

def ctx_name(ctx: SDTAContext | Contract[TaintedLabel]) -> str:
    if ctx == avl_ctx():
        return "avl"
    elif ctx == not_avl_wbf_ctx():
        return "not avl"
    elif ctx == avl_wbf_ctx():
        return "avl"
    elif ctx == not_avl_ctx():
        return "not avl"
    elif ctx == avl_wbf_ctx():
        return "avl wbf"
    elif ctx == bst_strict_ctx():
        return "bst strict"
    elif ctx == not_bst_strict_ctx():
        return "not bst strict"
    elif ctx == sll_sorted_strict_ctx():
        return "sll sorted strict"
    elif ctx == not_sll_sorted_strict_ctx():
        return "not sll sorted strict"
    elif ctx == not_bst_ctx():
        return "not bst"
    elif ctx == not_sll_sorted_ctx():
        return "not sll sorted"
    elif ctx == bst_ctx():
        return "bst"
    elif ctx == read_only_contract():
        return "read-only"
    else:
        raise ValueError(f"Unknown context: {ctx}")


benchamrks_config: list[BenchmarkConfig] = [
    # post_is_tree benchmarks
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_find.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_find.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_unsafe_circular.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_unsafe_post_1.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_unsafe_post_2.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_reverse.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_remove_root.c", post_ctx=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_insert.c", m=1, post_ctx=True),
    # pre_ctx benchmarks
    # BenchmarkConfig(file_name=C_FILES_DIR / "avl_safe_check_balance_and_root_height.c", pre_ctx=avl_ctx()),
    # BenchmarkConfig(file_name=C_FILES_DIR / "avl_unsafe_check_balance.c", pre_ctx=avl_ctx()),
    # BenchmarkConfig(file_name=C_FILES_DIR / "avl_unsafe_check_root_height.c", pre_ctx=avl_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_min_lt_max.c", pre_ctx=bst_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_unsafe_min_lt_max.c", pre_ctx=bst_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_sorted_safe_first_lt_last.c", pre_ctx=sll_sorted_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_sorted_unsafe_first_lt_last.c", pre_ctx=sll_sorted_strict_ctx()),
    # pre + post benchmarks
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_find.c", pre_ctx=bst_strict_ctx(), post_ctx=not_bst_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_insert.c", m=1, pre_ctx=bst_strict_ctx(), post_ctx=not_bst_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_insert.c", m=1, pre_ctx=bst_ctx(), post_ctx=not_bst_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_insert.c", m=1, pre_ctx=bst_ctx(), post_ctx=not_bst_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_find.c", pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_insert_sorted.c", m=1, pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_insert_sorted.c", m=1, pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "avl_safe_find.c", pre_ctx=avl_ctx(), post_ctx=not_avl_ctx()),
    # pre + contract
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_find.c", pre_ctx=bst_strict_ctx(), post_ctx=read_only_contract()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_insert.c", m=1, pre_ctx=bst_strict_ctx(), post_ctx=read_only_contract()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_find.c", pre_ctx=sll_sorted_strict_ctx(), post_ctx=read_only_contract()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_find.c", pre_ctx=sll_sorted_strict_ctx(), post_ctx=read_only_contract()),
    BenchmarkConfig(file_name=C_FILES_DIR / "avl_safe_find.c", m=1, pre_ctx=avl_ctx(), post_ctx=read_only_contract()),
]

def main():
    now = time.strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"benchmarks_{now}.csv"
    with open(file_name, "w") as f:
        fields = [
            "file_name",
            "n",
            "m",
            "c",
            "pre_ctx",
            "post_is_tree",
            "trivially_safe_for_err",
            "trivially_safe_for_oom",
            "trivially_safe_for_lof",
            "trivially_safe_for_post_is_tree",
            "labels_generation_elapsed_time",
            "labels_generation_timed_out",
            "system_err_creation_elapsed_time",
            "system_err_creation_timed_out",
            "solving_for_err_elapsed_time",
            "solving_for_err_timed_out",
            "system_oom_creation_elapsed_time",
            "system_oom_creation_timed_out",
            "solving_for_oom_elapsed_time",
            "solving_for_oom_timed_out",
            "system_lof_creation_elapsed_time",
            "system_lof_creation_timed_out",
            "solving_for_lof_elapsed_time",
            "solving_for_lof_timed_out",
            "system_post_is_tree_creation_elapsed_time",
            "system_post_is_tree_creation_timed_out",
            "solving_for_post_is_tree_elapsed_time",
            "solving_for_post_is_tree_timed_out",
            "outcome_for_err",
            "outcome_for_oom",
            "outcome_for_lof",
            "outcome_for_post_is_tree",
            "number_of_labels",
            "longest_label_len",
            "number_of_tainted_labels"
        ]
        dict_writer = csv.DictWriter(f, fieldnames=fields)
        dict_writer.writeheader()
        for config in benchamrks_config:
            print(f"Running benchmark for {config.file_name}")
            reset_env()
            result = run_benchmark(config, timeout=1500)
            row = {
                "file_name": config.file_name.name,
                "n": config.n,
                "m": config.m,
                "c": config.c,
                "pre_ctx": config.pre_ctx,
                "post_is_tree": config.post_ctx,
                "trivially_safe_for_err": result.trivially_safe_for["err"],
                "trivially_safe_for_oom": result.trivially_safe_for["oom"],
                "trivially_safe_for_lof": result.trivially_safe_for["lof"],
                "trivially_safe_for_post_is_tree": result.trivially_safe_for["post_is_tree"],
                "labels_generation_elapsed_time": result.labels_generation_elapsed_time,
                "labels_generation_timed_out": result.labels_generation_timed_out,
                "system_err_creation_elapsed_time": result.system_creation_elapsed_time_for["err"],
                "system_err_creation_timed_out": result.system_creation_timed_out_for["err"],
                "solving_for_err_elapsed_time": result.solving_elapsed_time_for["err"],
                "solving_for_err_timed_out": result.solving_timed_out_for["err"],
                "system_oom_creation_elapsed_time": result.system_creation_elapsed_time_for["oom"],
                "system_oom_creation_timed_out": result.system_creation_timed_out_for["oom"],
                "solving_for_oom_elapsed_time": result.solving_elapsed_time_for["oom"],
                "solving_for_oom_timed_out": result.solving_timed_out_for["oom"],
                "system_lof_creation_elapsed_time": result.system_creation_elapsed_time_for["lof"],
                "system_lof_creation_timed_out": result.system_creation_timed_out_for["lof"],
                "solving_for_lof_elapsed_time": result.solving_elapsed_time_for["lof"],
                "solving_for_lof_timed_out": result.solving_timed_out_for["lof"],
                "system_post_is_tree_creation_elapsed_time": result.system_creation_elapsed_time_for["post_is_tree"],
                "system_post_is_tree_creation_timed_out": result.system_creation_timed_out_for["post_is_tree"],
                "solving_for_post_is_tree_elapsed_time": result.solving_elapsed_time_for["post_is_tree"],
                "solving_for_post_is_tree_timed_out": result.solving_timed_out_for["post_is_tree"],
                "outcome_for_err": result.outcome_for["err"],
                "outcome_for_oom": result.outcome_for["oom"],
                "outcome_for_lof": result.outcome_for["lof"],
                "outcome_for_post_is_tree": result.outcome_for["post_is_tree"],
                "number_of_labels": result.number_of_chcs,
                "longest_label_len": result.longest_label_len,
                "number_of_tainted_labels": result.number_of_tainted_labels
            }
            for key, value in row.items():
                match value:
                    case None:
                        row[key] = "N/A"
                    case Enum():
                        row[key] = value.value
                    case float():
                        row[key] = round(value, 4)
                    case SDTAContext():
                        row[key] = ctx_name(value)
                    case _:
                        pass
            dict_writer.writerow(row)

if __name__ == "__main__":
    main()
