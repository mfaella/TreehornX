"""Memory safety of tree-manipulating programs through the compressed Lab CHC system.

Every label whose lace ends with a null-pointer dereference is queried: the system is sat when no
such label is reachable (the program is safe within the bounds m, n) and unsat otherwise.
"""

import shutil
from pathlib import Path

import pytest
from pychc.environment import reset_env
from pychc.solvers.witness import Status
from pychc.solvers.z3 import Z3CHCSolver

from treehornx.chc.Lab import make_system
from treehornx.enum_models.Lab import ERR, Lab
from treehornx.parser import parse_file

C_FILES = Path(__file__).parent / "c_files"
TIMEOUT = 120

# (program, m, n, expected status)
CASES = [
    ("sll_safe_find", 0, 12, Status.SAT),
    ("sll_unsafe_find", 0, 12, Status.UNSAT),
    ("sll_safe_insert_sorted", 1, 12, Status.SAT),
    ("sll_unsafe_insert", 1, 12, Status.UNSAT),
    ("sll_safe_length", 0, 12, Status.SAT),
    ("sll_unsafe_length", 0, 12, Status.UNSAT),
    # two passes over the list plus a rewind to the head need more frames per node
    ("sll_safe_find_last", 0, 16, Status.SAT),
    ("sll_unsafe_find_last", 0, 16, Status.UNSAT),
    ("bst_safe_find", 0, 12, Status.SAT),
    ("bst_unsafe_find", 0, 12, Status.UNSAT),
    ("bst_safe_insert", 1, 12, Status.SAT),
    ("bst_unsafe_insert", 1, 12, Status.UNSAT),
]


@pytest.fixture(autouse=True)
def fresh_smt_environment() -> None:
    """Labels are interned across programs, so the same `Lab<id>` can have a different signature in two
    programs: every test declares its predicates in a new pySMT environment."""
    reset_env()


def ends_with_error(label: Lab) -> bool:
    return label.next is None and isinstance(label.frame.event, ERR)


@pytest.mark.skipif(shutil.which("z3") is None, reason="z3 executable not found")
@pytest.mark.parametrize(("program", "m", "n", "expected"), CASES, ids=[case[0] for case in CASES])
def test_memory_safety(program: str, m: int, n: int, expected: Status) -> None:
    function = parse_file(str(C_FILES / f"{program}.c"))
    system = make_system(function, function.node.k, m, n, ends_with_error)

    solver = Z3CHCSolver()
    solver.load_system(system)

    assert solver.solve(timeout=TIMEOUT) == expected
