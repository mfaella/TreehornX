from pathlib import Path

import pytest
from pychc.solvers.chc_solver import CHCSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.golem import GolemSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.witness import Status
from pysmt.environment import reset_env

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.SDTAContext import SDTAContext, not_bst_ctx, not_bst_strict_ctx, not_sll_sorted_ctx, not_sll_sorted_strict_ctx, sll_sorted_ctx, sll_sorted_strict_ctx
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


def make_system_without_pre(function: Function, root: Var, trees: KnittedTrees, post_ctx: SDTAContext):
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct)
    system_factory = CHCSystemFactory(function, root.sort.pointee, trees, post_ctx=post_ctx, root_name=root.name)
    return system_factory.make_system()


def check_sat_without_pre(
    file_name: str,
    post_ctx: SDTAContext,
    solver: CHCSolver = default_solver(),
    n: int = DEFAULT_N,
    m: int = DEFAULT_M,
    c: int = DEFAULT_C,
) -> Status:
    function, root, trees = parse_and_generate_labels(file_name, n, m, c)
    system = make_system_without_pre(function, root, trees, post_ctx)
    solver.load_system(system)
    return solver.solve()


# --- bst_safe_find ---

def test_bst_safe_find_without_pre(): # ok
    result = check_sat_without_pre("bst_safe_find.c", post_ctx=not_bst_ctx())
    assert result == Status.UNSAT

def test_bst_safe_find_without_pre_strict(): # ok
    result = check_sat_without_pre("bst_safe_find.c", post_ctx=not_bst_strict_ctx())
    assert result == Status.UNSAT

# --- bst_safe_insert ---

def test_bst_safe_insert_without_pre(): # ok
    result = check_sat_without_pre("bst_safe_insert.c", post_ctx=not_bst_ctx(), m=1)
    assert result == Status.UNSAT

def test_bst_safe_insert_without_pre_strict(): # ok
    result = check_sat_without_pre("bst_safe_insert.c", post_ctx=not_bst_strict_ctx(), m=1)
    assert result == Status.UNSAT

# --- sll_safe_find ---

def test_sll_safe_find_without_pre(): # ok
    result = check_sat_without_pre("sll_safe_find.c", post_ctx=sll_sorted_ctx())
    assert result == Status.UNSAT

def test_sll_safe_find_without_pre_strict(): # ok
    result = check_sat_without_pre("sll_safe_find.c", post_ctx=sll_sorted_strict_ctx())
    assert result == Status.UNSAT

# --- sll_safe_insert_sorted ---

def test_sll_safe_insert_sorted_without_pre(): # ok
    result = check_sat_without_pre("sll_safe_insert_sorted.c", post_ctx=not_sll_sorted_ctx(), m=1)
    assert result == Status.UNSAT

def test_sll_safe_insert_sorted_without_pre_strict(): # ok
    result = check_sat_without_pre("sll_safe_insert_sorted.c", post_ctx=not_sll_sorted_strict_ctx(), m=1)
    assert result == Status.UNSAT
