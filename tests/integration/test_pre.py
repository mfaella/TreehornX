from pathlib import Path

import pytest
from pychc.solvers.chc_solver import CHCSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.golem import GolemSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.witness import Status
from pysmt.environment import reset_env

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.SDTAContext import SDTAContext, avl_ctx, bst_strict_ctx, sll_sorted_strict_ctx
from treehornx.enum_labels import KnittedTrees, generate_labels
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.ir.sorts import Pointer, Struct
from treehornx.parser.CParser import CParser


DEFAULT_M = 0
DEFAULT_C = 32
DEFAULT_N = 128

INTEGRATION_TESTS_DIR = Path(__file__).parent


@pytest.fixture(autouse=True)
def reset_pysmt_enviroment():
    reset_env()


def parse_and_generate_labels(file_name: str, n: int = DEFAULT_N, m: int = DEFAULT_M, c: int = DEFAULT_C):
    parser = CParser()
    file_path = INTEGRATION_TESTS_DIR / "c_files" / file_name
    function = next(iter(parser.parse_file(str(file_path))))
    root = next(var for var in function.vars if var.name == "root_0")
    trees = generate_labels(function, root, m, n, c)
    return function, root, trees


def default_solver() -> CHCSolver:
    binary_path = INTEGRATION_TESTS_DIR / "solvers"
    return GolemSolver(binary_path=binary_path)


def make_system_with_pre(
    function: Function,
    root: Var,
    trees: KnittedTrees,
    pre_ctx: SDTAContext,
    exit_code: ExitCodeKind,
    n: int = DEFAULT_N,
    m: int = DEFAULT_M,
    c: int = DEFAULT_C,
):
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct)
    system_factory = CHCSystemFactory(function, root.sort.pointee, trees, pre_ctx)
    system = system_factory.make_system(exit_code)
    return system


def check_sat_with_pre(
    file_name: str, pre_ctx: SDTAContext, exit_code: ExitCodeKind, solver: CHCSolver = default_solver()
) -> Status:
    function, root, trees = parse_and_generate_labels(file_name)
    system = make_system_with_pre(function, root, trees, pre_ctx, exit_code)
    solver.load_system(system)
    result = solver.solve()
    return result


def test_avl_safe_check_balance_and_root_height():
    pre_ctx = avl_ctx()
    result = check_sat_with_pre("avl_safe_check_balance_and_root_height.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.SAT, f"Expected SAT, got {result}"


def test_avl_unsafe_check_balance():
    pre_ctx = avl_ctx()
    result = check_sat_with_pre("avl_unsafe_check_balance.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.UNSAT, f"Expected UNSAT, got {result}"


def test_avl_unsafe_check_root_height():
    pre_ctx = avl_ctx()
    result = check_sat_with_pre("avl_unsafe_check_root_height.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.UNSAT, f"Expected UNSAT, got {result}"


def test_bst_safe_min_lt_max():
    pre_ctx = bst_strict_ctx()
    result = check_sat_with_pre("bst_safe_min_lt_max.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.SAT, f"Expected SAT, got {result}"


def test_bst_unsafe_min_lt_max():
    pre_ctx = bst_strict_ctx()
    result = check_sat_with_pre("bst_unsafe_min_lt_max.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.UNSAT, f"Expected UNSAT, got {result}"


def test_sll_sorted_safe_first_lt_last():
    pre_ctx = sll_sorted_strict_ctx()
    result = check_sat_with_pre("sll_sorted_safe_first_lt_last.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.SAT, f"Expected SAT, got {result}"


def test_sll_sorted_unsafe_first_lt_last():
    pre_ctx = sll_sorted_strict_ctx()
    result = check_sat_with_pre("sll_sorted_unsafe_first_lt_last.c", pre_ctx, ExitCodeKind.ERR)
    assert result == Status.UNSAT, f"Expected UNSAT, got {result}"
