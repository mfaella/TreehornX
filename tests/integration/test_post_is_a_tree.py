from pathlib import Path

import pytest
from pychc.solvers.chc_solver import CHCSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.golem import GolemSolver  # pyright: ignore[reportMissingTypeStubs]
from pychc.solvers.witness import Status
from pysmt.environment import reset_env

from treehornx.chc.CHCSystemFactory import CHCSystemFactory
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.SDTAContext import SDTAContext, avl_strict_ctx, bst_strict_ctx, sll_sorted_strict_ctx
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


def make_system(function: Function, root: Var, trees: KnittedTrees):
    assert isinstance(root.sort, Pointer) and isinstance(root.sort.pointee, Struct)
    system_factory = CHCSystemFactory(function, root.sort.pointee, trees, post_ctx=True, root_name=root.name)
    system = system_factory.make_system()
    return system


def check_sat(
    file_name: str, solver: CHCSolver = default_solver(), n: int = DEFAULT_N, m: int = DEFAULT_M, c: int = DEFAULT_C
) -> Status:
    function, root, trees = parse_and_generate_labels(file_name, n, m, c)
    system = make_system(function, root, trees)
    solver.load_system(system)
    result = solver.solve()
    return result


def test_bst_safe_find():
    result = check_sat("bst_safe_find.c")
    assert result == Status.SAT


def test_sll_safe_find():
    result = check_sat("sll_safe_find.c")
    assert result == Status.SAT


def test_sll_unsafe_circular():
    result = check_sat("sll_unsafe_circular.c")
    assert result == Status.UNSAT


def test_bst_unsafe_post_1():
    result = check_sat("bst_unsafe_post_1.c")
    assert result == Status.UNSAT


def test_bst_unsafe_post_2():
    result = check_sat("bst_unsafe_post_2.c")
    assert result == Status.UNSAT


def test_sll_safe_reverse():
    result = check_sat("sll_safe_reverse.c")
    assert result == Status.SAT


def test_bst_safe_remove_root():
    result = check_sat("bst_safe_remove_root.c")
    assert result == Status.SAT


def test_bst_safe_insert():
    result = check_sat("bst_safe_insert.c", m=1)
    assert result == Status.SAT
