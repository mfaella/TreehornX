import csv
from enum import Enum
import time

from dataclasses import dataclass, field
from pathlib import Path

from pychc.solvers.chc_solver import CHCSolver, Status # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.golem import GolemSolver # pyright: ignore[reportMissingTypeStubs]
from pysmt.shortcuts import reset_env

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.pre import PreContext
from treehornx.chc.pre.PreContext import avl_strict_ctx, bst_strict_ctx, sll_sorted_strict_ctx
from treehornx.enum_labels import generate_labels
from treehornx.ir.sorts import Pointer, Struct
from treehornx.parser.CParser import CParser

DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_C = 32

def default_chc_solver() -> CHCSolver:
    path = Path(__file__).parent / "solvers" / "linux" / "x86-64"
    return GolemSolver(binary_path=path)

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
    pre_ctx: PreContext|None = None
    post_is_tree: bool = False
    solver: CHCSolver = field(default_factory = default_chc_solver)

@dataclass
class BenchmarkResult:
    trivially_safe_for_err: bool | None = None
    trivially_safe_for_oom: bool | None = None
    trivially_safe_for_lof: bool | None = None
    trivially_safe_for_post_is_tree: bool | None = None
    labels_generation_elapsed_time: float | None = None
    solving_for_err_elapsed_time: float | None = None
    solving_for_oom_elapsed_time: float | None = None
    solving_for_lof_elapsed_time: float | None = None
    solving_for_post_is_tree_elapsed_time: float | None = None
    system_err_creation_elapsed_time: float | None = None
    system_oom_creation_elapsed_time: float | None = None
    system_lof_creation_elapsed_time: float | None = None
    system_post_is_tree_creation_elapsed_time: float | None = None
    outcome_for_err: VerificationOutcome | None = None
    outcome_for_oom: VerificationOutcome | None = None
    outcome_for_lof: VerificationOutcome | None = None
    outcome_for_post_is_tree: VerificationOutcome | None = None

def status_to_outcome(status: Status) -> VerificationOutcome:
    if status == Status.SAT:
        return VerificationOutcome.SAFE
    elif status == Status.UNSAT:
        return VerificationOutcome.UNSAFE
    else:
        return VerificationOutcome.UNKNOWN

def run_benchmark(config: BenchmarkConfig):
    parser = CParser()
    function = next(iter(parser.parse_file(str(config.file_name))))
    root = next(var for var in function.vars if var.name == "root_0")
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct)
    result = BenchmarkResult()
    start_time = time.perf_counter()
    trees = generate_labels(function, root, config.m, config.n, config.c)
    end_time = time.perf_counter()
    result.labels_generation_elapsed_time = end_time - start_time
    system_factory = CHCSystemFactory(
        function,
        root.sort.pointee,
        trees,
        config.pre_ctx,
        config.post_is_tree,
        root.name
    )
    if config.post_is_tree:
        result.trivially_safe_for_post_is_tree = system_factory.trivially_safe_for_post_is_tree

    if not system_factory.trivially_safe_for_err:
        result.trivially_safe_for_err = False
        start = time.perf_counter()
        system = system_factory.make_system(ExitCodeKind.ERR)
        end = time.perf_counter()
        result.system_err_creation_elapsed_time = end - start
        start = time.perf_counter()
        config.solver.load_system(system)
        status = config.solver.solve()
        result.outcome_for_err = status_to_outcome(status)
        end = time.perf_counter()
        result.solving_for_err_elapsed_time = end - start
    else:
        result.outcome_for_err = VerificationOutcome.SAFE
        result.trivially_safe_for_err = True

    if not system_factory.trivially_safe_for_oom:
        result.trivially_safe_for_oom = False
        start = time.perf_counter()
        system = system_factory.make_system(ExitCodeKind.OOM)
        end = time.perf_counter()
        result.system_oom_creation_elapsed_time = end - start
        start = time.perf_counter()
        config.solver.load_system(system)
        status = config.solver.solve()
        end = time.perf_counter()
        result.outcome_for_oom = status_to_outcome(status)
        result.solving_for_oom_elapsed_time = end - start
    else:
        result.trivially_safe_for_oom = True
        result.outcome_for_oom = VerificationOutcome.SAFE

    if not system_factory.trivially_safe_for_lof:
        result.trivially_safe_for_lof = False
        start = time.perf_counter()
        system = system_factory.make_system(ExitCodeKind.LABEL_OVERFLOW)
        end = time.perf_counter()
        result.system_lof_creation_elapsed_time = end - start
        start = time.perf_counter()
        config.solver.load_system(system)
        status = config.solver.solve()
        end = time.perf_counter()
        result.outcome_for_lof = status_to_outcome(status)
        result.solving_for_lof_elapsed_time = end - start
    else:
        result.trivially_safe_for_lof = True
        result.outcome_for_lof = VerificationOutcome.SAFE

    if (
        system_factory.trivially_safe_for_err and
        system_factory.trivially_safe_for_oom and
        system_factory.trivially_safe_for_lof and
        config.post_is_tree and
        not result.trivially_safe_for_post_is_tree
    ):
        start = time.perf_counter()
        system = system_factory.make_system()
        end = time.perf_counter()
        result.system_post_is_tree_creation_elapsed_time = end - start
        start = time.perf_counter()
        config.solver.load_system(system)
        status = config.solver.solve()
        end = time.perf_counter()
        result.outcome_for_post_is_tree = status_to_outcome(status)
        result.solving_for_post_is_tree_elapsed_time = end - start

    return result

def pre_ctx_name(pre_ctx: PreContext) -> str:
    if pre_ctx == avl_strict_ctx():
        return "avl strict"
    elif pre_ctx == bst_strict_ctx():
        return "bst strict_ctx"
    elif pre_ctx == sll_sorted_strict_ctx():
        return "sll sorted strict"
    else:
        raise ValueError("Unknown pre-context")

C_FILES_DIR = Path(__file__).parent / "c_files"

benchamrks_config: list[BenchmarkConfig] = [
    # post_is_tree benchmarks
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_find.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_find.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_unsafe_circular.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_unsafe_post_1.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_unsafe_post_2.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_safe_reverse.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_remove_root.c", post_is_tree=True),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_insert.c", m=1, post_is_tree=True),
    # pre_ctx benchmarks
    BenchmarkConfig(file_name=C_FILES_DIR / "avl_safe_check_balance_and_root_height.c", pre_ctx=avl_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "avl_unsafe_check_balance.c", pre_ctx=avl_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "avl_unsafe_check_root_height.c", pre_ctx=avl_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_safe_min_lt_max.c", pre_ctx=bst_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "bst_unsafe_min_lt_max.c", pre_ctx=bst_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_sorted_safe_first_lt_last.c", pre_ctx=sll_sorted_strict_ctx()),
    BenchmarkConfig(file_name=C_FILES_DIR / "sll_sorted_unsafe_first_lt_last.c", pre_ctx=sll_sorted_strict_ctx()),
]

def main():
    with open("benchmarks.csv", "w") as f:
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
            "system_err_creation_elapsed_time",
            "solving_for_err_elapsed_time",
            "system_oom_creation_elapsed_time",
            "solving_for_oom_elapsed_time",
            "system_lof_creation_elapsed_time",
            "solving_for_lof_elapsed_time",
            "system_post_is_tree_creation_elapsed_time",
            "solving_for_post_is_tree_elapsed_time",
            "outcome_for_err",
            "outcome_for_oom",
            "outcome_for_lof",
            "outcome_for_post_is_tree"
        ]
        dict_writer = csv.DictWriter(f, fieldnames=fields)
        dict_writer.writeheader()
        for config in benchamrks_config:
            print(f"Running benchmark for {config.file_name}")
            reset_env()
            result = run_benchmark(config)
            row = {
                "file_name": config.file_name.name,
                "n": config.n,
                "m": config.m,
                "c": config.c,
                "pre_ctx": config.pre_ctx,
                "post_is_tree": config.post_is_tree,
                "trivially_safe_for_err": result.trivially_safe_for_err,
                "trivially_safe_for_oom": result.trivially_safe_for_oom,
                "trivially_safe_for_lof": result.trivially_safe_for_lof,
                "trivially_safe_for_post_is_tree": result.trivially_safe_for_post_is_tree,
                "labels_generation_elapsed_time": result.labels_generation_elapsed_time,
                "system_err_creation_elapsed_time": result.system_err_creation_elapsed_time,
                "solving_for_err_elapsed_time": result.solving_for_err_elapsed_time,
                "system_oom_creation_elapsed_time": result.system_oom_creation_elapsed_time,
                "solving_for_oom_elapsed_time": result.solving_for_oom_elapsed_time,
                "system_lof_creation_elapsed_time": result.system_lof_creation_elapsed_time,
                "solving_for_lof_elapsed_time": result.solving_for_lof_elapsed_time,
                "system_post_is_tree_creation_elapsed_time": result.system_post_is_tree_creation_elapsed_time,
                "solving_for_post_is_tree_elapsed_time": result.solving_for_post_is_tree_elapsed_time,
                "outcome_for_err": result.outcome_for_err,
                "outcome_for_oom": result.outcome_for_oom,
                "outcome_for_lof": result.outcome_for_lof,
                "outcome_for_post_is_tree": result.outcome_for_post_is_tree
            }
            for key, value in row.items():
                if value is None:
                    row[key] = "N/A"
                if isinstance(value, Enum):
                    row[key] = value.value
            if isinstance(row["pre_ctx"], PreContext):
                row["pre_ctx"] = pre_ctx_name(row["pre_ctx"])
            dict_writer.writerow(row)

if __name__ == "__main__":
    main()
