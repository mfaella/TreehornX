"""Output checks through the DFS lace: tree shape of the output heap and postconditions.

The system is sat when every execution ending at `exit` produces a tree (structure mode) that, when a negated
postcondition is given, is not accepted by it.
"""

import shutil
from pathlib import Path
from typing import Callable

import pytest
from pychc.environment import reset_env
from pychc.solvers.witness import Status
from pychc.solvers.golem import GolemSolver

from treehornx.chc import post
from treehornx.chc.sdta.SDTAContext import SDTAContext, not_sll_sorted_ctx, not_sll_sorted_strict_ctx
from treehornx.parser import parse_file

C_FILES = Path(__file__).parent / "c_files"
SOLVERS = Path(__file__).parent / "solvers"
TIMEOUT = 120
N = 128
N_DFS = 64

# (program, m, expected status)
STRUCTURE_CASES = [
    ("sll_safe_reverse", 0, Status.SAT),
    ("sll_safe_insert_sorted", 1, Status.SAT),
    ("bst_safe_insert", 1, Status.SAT),
    ("sll_unsafe_circular", 0, Status.UNSAT),  # the last node points to the head: Loop
    ("bst_unsafe_post_2", 0, Status.UNSAT),  # the leftmost node points to the root: Loop
    ("bst_unsafe_post_1", 0, Status.UNSAT),  # the right child gets two parents: Conv
]

# (program, negated postcondition, m, expected status); no precondition, every input list is considered
POST_CASES: list[tuple[str, Callable[[], SDTAContext], int, Status]] = [
    ("sll_post_set_zero", not_sll_sorted_ctx, 0, Status.SAT),  # all zeros: sorted
    ("sll_post_set_zero", not_sll_sorted_strict_ctx, 0, Status.UNSAT),  # two zeros are not strictly sorted
    ("sll_safe_find", not_sll_sorted_ctx, 0, Status.UNSAT),  # the input list is left as it is
]

pytestmark = pytest.mark.skipif(shutil.which("golem", path=str(SOLVERS)) is None, reason="golem executable not found")


@pytest.fixture(autouse=True)
def fresh_smt_environment() -> None:
    """Labels are interned across programs, so the same predicate name can have a different signature in two
    programs: every test declares its predicates in a new pySMT environment."""
    reset_env()


def solve(program: str, m: int, ctx: SDTAContext | None, n_dfs: int = N_DFS, check_overflow: bool = True) -> Status:
    function = parse_file(str(C_FILES / f"{program}.c"))
    solver = GolemSolver(binary_path=SOLVERS)
    system = post.make_system(function, function.node.k, m, N, n_dfs, ctx, check_overflow=check_overflow)
    solver.load_system(system)
    return solver.solve(timeout=TIMEOUT)


@pytest.mark.parametrize(("program", "m", "expected"), STRUCTURE_CASES, ids=[case[0] for case in STRUCTURE_CASES])
def test_output_is_a_tree(program: str, m: int, expected: Status) -> None:
    assert solve(program, m, None) == expected


@pytest.mark.parametrize(
    ("program", "postcondition", "m", "expected"),
    POST_CASES,
    ids=[f"{case[0]}-{case[1].__name__}" for case in POST_CASES],
)
def test_postcondition(program: str, postcondition: Callable[[], SDTAContext], m: int, expected: Status) -> None:
    assert solve(program, m, postcondition()) == expected


@pytest.mark.parametrize(("check_overflow", "expected"), [(True, Status.UNSAT), (False, Status.SAT)])
def test_dfs_overflow(check_overflow: bool, expected: Status) -> None:
    """With too few DFS frames the visit of a safe program cannot complete: the overflow is reported."""
    assert solve("sll_safe_reverse", 0, None, n_dfs=4, check_overflow=check_overflow) == expected
