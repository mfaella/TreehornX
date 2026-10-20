"""Memory safety under a precondition through the Lab CHC system and the precondition layer.

The system is sat when no input accepted by the precondition leads to a null-pointer dereference. The
"safe" programs below are safe only thanks to the precondition: without it they can dereference nil.
"""

import shutil
from pathlib import Path
from typing import Callable

import pytest
from pychc.chc_system import CHCSystem
from pychc.environment import reset_env
from pychc.solvers.witness import Status
from pychc.solvers.z3 import Z3CHCSolver

from treehornx.chc import Lab, pre
from treehornx.chc.sdta.SDTAContext import SDTAContext, avl_ctx, bst_strict_ctx, sll_sorted_ctx, sll_sorted_strict_ctx
from treehornx.enum_models.Lab import ERR
from treehornx.enum_models.Lab import Lab as Label
from treehornx.parser import parse_file

C_FILES = Path(__file__).parent / "c_files"
TIMEOUT = 120
N = 128

# (program, precondition, m, expected status)
CASES: list[tuple[str, Callable[[], SDTAContext], int, Status]] = [
    ("sll_sorted_safe_first_lt_last", sll_sorted_strict_ctx, 0, Status.SAT),
    ("sll_sorted_unsafe_first_lt_last", sll_sorted_strict_ctx, 0, Status.UNSAT),
    ("bst_safe_min_lt_max", bst_strict_ctx, 0, Status.SAT),
    ("bst_unsafe_min_lt_max", bst_strict_ctx, 0, Status.UNSAT),
    # safe for every input, the precondition must not change the result
    ("sll_safe_find", sll_sorted_ctx, 0, Status.SAT),
    ("bst_safe_insert_field_nil", bst_strict_ctx, 1, Status.SAT),
    ("avl_safe_insert_bal", avl_ctx, 1, Status.SAT),
]

# safe only thanks to the precondition
NEEDS_PRECONDITION = ["sll_sorted_safe_first_lt_last", "bst_safe_min_lt_max"]

pytestmark = pytest.mark.skipif(shutil.which("z3") is None, reason="z3 executable not found")


@pytest.fixture(autouse=True)
def fresh_smt_environment() -> None:
    """Labels are interned across programs, so the same predicate name can have a different signature in two
    programs: every test declares its predicates in a new pySMT environment."""
    reset_env()


def solve(system: CHCSystem) -> Status:
    solver = Z3CHCSolver()
    solver.load_system(system)
    return solver.solve(timeout=TIMEOUT)


def ends_with_error(label: Label) -> bool:
    return isinstance(label.frame.event, ERR)


@pytest.mark.parametrize(("program", "precondition", "m", "expected"), CASES, ids=[case[0] for case in CASES])
def test_memory_safety_under_precondition(
    program: str, precondition: Callable[[], SDTAContext], m: int, expected: Status
) -> None:
    function = parse_file(str(C_FILES / f"{program}.c"))
    system = pre.make_system(function, function.node.k, m, N, precondition())

    assert solve(system) == expected


@pytest.mark.parametrize("program", NEEDS_PRECONDITION)
def test_unsafe_without_precondition(program: str) -> None:
    function = parse_file(str(C_FILES / f"{program}.c"))
    system = Lab.make_system(function, function.node.k, 0, N, ends_with_error)

    assert solve(system) == Status.UNSAT
