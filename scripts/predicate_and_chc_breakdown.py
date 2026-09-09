"""Run the same verifications as the integration test suite and report, for each
one, how many predicates and CHCs were produced by each phase of
``CHCSystemFactory.make_system``: Lab, Pre, T and S.

The test cases below mirror exactly the ones in:
    tests/integration/test_pre.py
    tests/integration/test_post.py
    tests/integration/test_pre_post.py
    tests/integration/test_post_is_a_tree.py

Usage:
    python scripts/predicate_and_chc_breakdown.py
"""

from collections.abc import Callable
from dataclasses import dataclass
import argparse
from functools import wraps
from pathlib import Path
from typing import Any
import csv
import time

from pychc.chc_system import CHCSystem  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.chc_solver import CHCSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.golem import GolemSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.witness import Status
from pysmt.environment import reset_env

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.SDTAContext import (
    SDTAContext,
    avl_ctx,
    bst_ctx,
    bst_strict_ctx,
    not_bst_ctx,
    not_bst_strict_ctx,
    not_sll_sorted_ctx,
    not_sll_sorted_strict_ctx,
    sll_sorted_ctx,
    sll_sorted_strict_ctx,
)
from treehornx.enum_labels import generate_labels
from treehornx.ir.sorts import Pointer, Struct
from treehornx.parser.CParser import CParser

DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_C = 32
DEFAULT_TIMEOUT = 1500

C_FILES_DIR = Path(__file__).parent.parent / "tests" / "integration" / "c_files"


def default_solver() -> CHCSolver:
    binary_path = Path(__file__).parent.parent / "tests" / "integration" / "solvers"
    return GolemSolver(binary_path=binary_path)


# The private methods of CHCSystemFactory that contribute predicates/CHCs for
# each of the four phases of `make_system`.
PHASE_METHODS: dict[str, tuple[str, ...]] = {
    "lab": ("_add_lab", "_add_lab_queries"),
    "pre": ("_add_pre", "_add_pre_queries"),
    "t": ("_add_T", "_add_T_queries"),
    "s": ("_add_S", "_add_contract"),
}


def instrument_factory(factory: CHCSystemFactory) -> dict[str, dict[str, int]]:
    """Monkey-patch `factory`'s phase methods so that every predicate/CHC they
    add to a CHCSystem is attributed to the right phase (Lab, Pre, T or S).

    Returns the (initially zeroed) counts dict that will be filled in place as
    `factory.make_system(...)` runs.
    """
    counts: dict[str, dict[str, int]] = {phase: {"predicates": 0, "chcs": 0} for phase in PHASE_METHODS}

    def make_wrapper(original: Callable[..., Any], phase: str) -> Callable[..., Any]:
        @wraps(original)
        def wrapper(system: CHCSystem, *args: Any, **kwargs: Any) -> Any:
            predicates_before = len(system.get_predicates())
            chcs_before = len(system.get_clauses())
            result = original(system, *args, **kwargs)
            counts[phase]["predicates"] += len(system.get_predicates()) - predicates_before
            counts[phase]["chcs"] += len(system.get_clauses()) - chcs_before
            return result

        return wrapper

    for phase, method_names in PHASE_METHODS.items():
        for method_name in method_names:
            original = getattr(factory, method_name)
            setattr(factory, method_name, make_wrapper(original, phase))

    return counts


@dataclass
class VerificationCase:
    name: str
    category: str
    file_name: str
    expected: Status
    n: int = DEFAULT_N
    m: int = DEFAULT_M
    c: int = DEFAULT_C
    pre_ctx: SDTAContext | None = None
    post_ctx: SDTAContext | bool | None = None
    exit_code: ExitCodeKind | None = None
    timeout: int = DEFAULT_TIMEOUT


# --- test_pre.py -------------------------------------------------------

PRE_CASES: list[VerificationCase] = [
    VerificationCase(
        "test_avl_safe_check_balance_and_root_height", "pre",
        "avl_safe_check_balance_and_root_height.c", Status.SAT,
        pre_ctx=avl_ctx(), exit_code=ExitCodeKind.ERR,
    ),
    VerificationCase(
        "test_avl_unsafe_check_balance", "pre",
        "avl_unsafe_check_balance.c", Status.UNSAT,
        pre_ctx=avl_ctx(), exit_code=ExitCodeKind.ERR,
    ),
    VerificationCase(
        "test_avl_unsafe_check_root_height", "pre",
        "avl_unsafe_check_root_height.c", Status.UNSAT,
        pre_ctx=avl_ctx(), exit_code=ExitCodeKind.ERR,
    ),
    VerificationCase(
        "test_bst_safe_min_lt_max", "pre",
        "bst_safe_min_lt_max.c", Status.SAT,
        pre_ctx=bst_strict_ctx(), exit_code=ExitCodeKind.ERR,
    ),
    VerificationCase(
        "test_bst_unsafe_min_lt_max", "pre",
        "bst_unsafe_min_lt_max.c", Status.UNSAT,
        pre_ctx=bst_strict_ctx(), exit_code=ExitCodeKind.ERR,
    ),
    VerificationCase(
        "test_sll_sorted_safe_first_lt_last", "pre",
        "sll_sorted_safe_first_lt_last.c", Status.SAT,
        pre_ctx=sll_sorted_strict_ctx(), exit_code=ExitCodeKind.ERR,
    ),
    VerificationCase(
        "test_sll_sorted_unsafe_first_lt_last", "pre",
        "sll_sorted_unsafe_first_lt_last.c", Status.UNSAT,
        pre_ctx=sll_sorted_strict_ctx(), exit_code=ExitCodeKind.ERR,
    ),
]

# --- test_post.py -------------------------------------------------------

POST_CASES: list[VerificationCase] = [
    VerificationCase(
        "test_bst_safe_find_without_pre", "post",
        "bst_safe_find.c", Status.UNSAT, post_ctx=not_bst_ctx(),
    ),
    VerificationCase(
        "test_bst_safe_find_without_pre_strict", "post",
        "bst_safe_find.c", Status.UNSAT, post_ctx=not_bst_strict_ctx(),
    ),
    VerificationCase(
        "test_bst_safe_insert_without_pre", "post",
        "bst_safe_insert.c", Status.UNSAT, m=1, post_ctx=not_bst_ctx(),
    ),
    VerificationCase(
        "test_bst_safe_insert_without_pre_strict", "post",
        "bst_safe_insert.c", Status.UNSAT, m=1, post_ctx=not_bst_strict_ctx(),
    ),
    VerificationCase(
        "test_sll_safe_find_without_pre", "post",
        "sll_safe_find.c", Status.UNSAT, post_ctx=sll_sorted_ctx(),
    ),
    VerificationCase(
        "test_sll_safe_find_without_pre_strict", "post",
        "sll_safe_find.c", Status.UNSAT, post_ctx=sll_sorted_strict_ctx(),
    ),
    VerificationCase(
        "test_sll_safe_insert_sorted_without_pre", "post",
        "sll_safe_insert_sorted.c", Status.UNSAT, m=1, post_ctx=not_sll_sorted_ctx(),
    ),
    VerificationCase(
        "test_sll_safe_insert_sorted_without_pre_strict", "post",
        "sll_safe_insert_sorted.c", Status.UNSAT, m=1, post_ctx=not_sll_sorted_strict_ctx(),
    ),
]

# --- test_pre_post.py -----------------------------------------------------

PRE_POST_CASES: list[VerificationCase] = [
    VerificationCase(
        "test_bst_safe_find_with_pre", "pre_post",
        "bst_safe_find.c", Status.SAT, pre_ctx=bst_ctx(), post_ctx=not_bst_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_bst_safe_find_with_strict_pre", "pre_post",
        "bst_safe_find.c", Status.SAT, pre_ctx=bst_strict_ctx(), post_ctx=not_bst_strict_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_bst_safe_insert_with_pre", "pre_post",
        "bst_safe_insert.c", Status.SAT, m=1, pre_ctx=bst_ctx(), post_ctx=not_bst_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_bst_safe_insert_with_strict_pre", "pre_post",
        "bst_safe_insert.c", Status.UNSAT, m=1, pre_ctx=bst_strict_ctx(), post_ctx=not_bst_strict_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_sll_safe_find_with_pre", "pre_post",
        "sll_safe_find.c", Status.SAT, pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_sll_safe_find_with_pre_strict", "pre_post",
        "sll_safe_find.c", Status.SAT, pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_strict_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_sll_safe_insert_sorted_with_pre", "pre_post",
        "sll_safe_insert_sorted.c", Status.SAT, m=1, pre_ctx=sll_sorted_ctx(), post_ctx=not_sll_sorted_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_sll_safe_insert_sorted_with_pre_strict", "pre_post",
        "sll_safe_insert_sorted.c", Status.UNSAT, m=1, pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_strict_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_sll_safe_insert_sorted_with_pre_strict_and_post_non_strict", "pre_post",
        "sll_safe_insert_sorted.c", Status.SAT, m=1, pre_ctx=sll_sorted_strict_ctx(), post_ctx=not_sll_sorted_ctx(), timeout=1200,
    ),
    VerificationCase(
        "test_sll_safe_insert_sorted_with_pre_non_strict_and_post_strict", "pre_post",
        "sll_safe_insert_sorted.c", Status.UNSAT, m=1, pre_ctx=sll_sorted_ctx(), post_ctx=not_sll_sorted_strict_ctx(), timeout=1200,
    ),
]

# --- test_post_is_a_tree.py ------------------------------------------------

POST_IS_TREE_CASES: list[VerificationCase] = [
    VerificationCase("test_bst_safe_find", "post_is_tree", "bst_safe_find.c", Status.SAT, post_ctx=True),
    VerificationCase("test_sll_safe_find", "post_is_tree", "sll_safe_find.c", Status.SAT, post_ctx=True),
    VerificationCase("test_sll_unsafe_circular", "post_is_tree", "sll_unsafe_circular.c", Status.UNSAT, post_ctx=True),
    VerificationCase("test_bst_unsafe_post_1", "post_is_tree", "bst_unsafe_post_1.c", Status.UNSAT, post_ctx=True),
    VerificationCase("test_bst_unsafe_post_2", "post_is_tree", "bst_unsafe_post_2.c", Status.UNSAT, post_ctx=True),
    VerificationCase("test_sll_safe_reverse", "post_is_tree", "sll_safe_reverse.c", Status.SAT, post_ctx=True),
    VerificationCase("test_bst_safe_remove_root", "post_is_tree", "bst_safe_remove_root.c", Status.SAT, post_ctx=True),
    VerificationCase("test_bst_safe_insert", "post_is_tree", "bst_safe_insert.c", Status.SAT, m=1, post_ctx=True),
]

ALL_CASES: list[VerificationCase] = [*PRE_CASES, *POST_CASES, *PRE_POST_CASES, *POST_IS_TREE_CASES]


def ctx_name(ctx: SDTAContext | bool | None) -> str:
    if ctx is None:
        return "N/A"
    if isinstance(ctx, bool):
        return str(ctx)
    if ctx == avl_ctx():
        return "avl"
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
    elif ctx == sll_sorted_ctx():
        return "sll sorted"
    else:
        raise ValueError(f"Unknown context: {ctx}")


def run_case(case: VerificationCase, solve: bool = True) -> dict[str, Any]:
    reset_env()

    parser = CParser()
    file_path = C_FILES_DIR / case.file_name
    function = next(iter(parser.parse_file(str(file_path))))
    root = next(var for var in function.vars if var.name == "root_0")
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct)

    trees = generate_labels(function, root, case.m, case.n, case.c)

    system_factory = CHCSystemFactory(
        function,
        root.sort.pointee,
        trees,
        pre_ctx=case.pre_ctx,
        post_ctx=case.post_ctx if case.post_ctx is not None else False,
        root_name=root.name if case.post_ctx else None,
    )

    counts = instrument_factory(system_factory)

    start = time.perf_counter()
    system = system_factory.make_system(case.exit_code)
    creation_elapsed = time.perf_counter() - start

    # The predicate/CHC counts are already complete at this point: solving is
    # only needed for the outcome columns, so a solver failure (e.g. the OOM
    # killer terminating the solver on a big system) must not lose the counts
    # nor abort the remaining cases.
    actual_status = "not solved"
    solving_elapsed = None
    if solve:
        solver = default_solver()
        solver.load_system(system)
        start = time.perf_counter()
        try:
            actual_status = solver.solve(timeout=case.timeout).value
        except Exception as exception:  # noqa: BLE001 - report and keep going
            actual_status = f"error: {type(exception).__name__}"
            print(f"  solver failed: {exception}")
        solving_elapsed = round(time.perf_counter() - start, 4)

    predicates_total = sum(counts[phase]["predicates"] for phase in counts)
    chcs_total = sum(counts[phase]["chcs"] for phase in counts)

    return {
        "test_name": case.name,
        "category": case.category,
        "file_name": case.file_name,
        "n": case.n,
        "m": case.m,
        "c": case.c,
        "pre_ctx": ctx_name(case.pre_ctx),
        "post_ctx": ctx_name(case.post_ctx),
        "expected_status": case.expected.value,
        "actual_status": actual_status,
        "system_creation_elapsed_time": round(creation_elapsed, 4),
        "solving_elapsed_time": solving_elapsed if solving_elapsed is not None else "N/A",
        "predicates_lab": counts["lab"]["predicates"],
        "predicates_pre": counts["pre"]["predicates"],
        "predicates_t": counts["t"]["predicates"],
        "predicates_s": counts["s"]["predicates"],
        "predicates_total": predicates_total,
        "chcs_lab": counts["lab"]["chcs"],
        "chcs_pre": counts["pre"]["chcs"],
        "chcs_t": counts["t"]["chcs"],
        "chcs_s": counts["s"]["chcs"],
        "chcs_total": chcs_total,
    }


FIELDS = [
    "test_name",
    "category",
    "file_name",
    "n",
    "m",
    "c",
    "pre_ctx",
    "post_ctx",
    "expected_status",
    "actual_status",
    "system_creation_elapsed_time",
    "solving_elapsed_time",
    "predicates_lab",
    "predicates_pre",
    "predicates_t",
    "predicates_s",
    "predicates_total",
    "chcs_lab",
    "chcs_pre",
    "chcs_t",
    "chcs_s",
    "chcs_total",
]


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument(
        "--no-solve",
        action="store_true",
        help=(
            "only build the CHC systems and count predicates/CHCs per phase, "
            "without running the solver (much faster, and avoids the very large "
            "memory usage the solver reaches on some pre+post systems)"
        ),
    )
    arg_parser.add_argument(
        "--only",
        default=None,
        help="run only the cases whose category matches this value (pre, post, pre_post, post_is_tree)",
    )
    args = arg_parser.parse_args()

    cases = [case for case in ALL_CASES if args.only is None or case.category == args.only]

    now = time.strftime("%Y-%m-%d_%H-%M-%S")
    out_path = Path(f"predicate_and_chc_breakdown_{now}.csv")
    failed: list[str] = []
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for case in cases:
            print(f"Running {case.name} ({case.file_name})...")
            try:
                row = run_case(case, solve=not args.no_solve)
            except Exception as exception:  # noqa: BLE001 - one bad case must not lose the rest
                print(f"  FAILED: {type(exception).__name__}: {exception}")
                failed.append(case.name)
                continue
            if not args.no_solve and row["actual_status"] != row["expected_status"]:
                print(f"  WARNING: expected {row['expected_status']}, got {row['actual_status']}")
            writer.writerow(row)
            f.flush()
    print(f"Wrote {len(cases) - len(failed)}/{len(cases)} results to {out_path}")
    if failed:
        print(f"Failed cases: {', '.join(failed)}")


if __name__ == "__main__":
    main()
