"""Hoare triples {pre} P {post} (POPL Sec. 8), checked in two steps:

1. memory safety under the precondition with Ex = {E, O, M}: no input accepted by the precondition leads to a
   memory error, to an out-of-memory or to a label overflow, so every execution ends at `exit` within the
   bounds (sat);
2. the postcondition under the precondition: every execution ending at `exit` on an accepted input produces a
   tree that is not accepted by the negated postcondition (sat).

Step 1 also guarantees that the bound n is large enough: with a smaller bound the executions overflow before
reaching `exit` and step 2 would hold vacuously.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
from pychc.chc_system import CHCSystem
from pychc.environment import reset_env
from pychc.solvers.golem import GolemSolver
from pychc.solvers.witness import Status

from treehornx.chc import post, pre
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.sdta.SDTAContext import (
    SDTAContext,
    avl_ctx,
    bst_ctx,
    bst_strict_ctx,
    not_avl_ctx,
    not_bst_ctx,
    not_bst_strict_ctx,
    not_sll_sorted_ctx,
    sll_sorted_ctx,
)
from treehornx.parser import parse_file

C_FILES = Path(__file__).parent / "c_files"
SOLVERS = Path(__file__).parent / "solvers"
TIMEOUT = 1800
N = 128
N_DFS = 64
ALL_EXITS = frozenset({ExitCodeKind.ERR, ExitCodeKind.OOM, ExitCodeKind.LABEL_OVERFLOW})


@dataclass(frozen=True)
class Triple:
    program: str
    pre: Callable[[], SDTAContext]
    post: Callable[[], SDTAContext]
    """Negation of the postcondition."""
    m: int


TRIPLES = [
    pytest.param(Triple("sll_safe_insert_sorted", sll_sorted_ctx, not_sll_sorted_ctx, 1), id="sll_safe_insert_sorted"),
    pytest.param(Triple("bst_safe_insert", bst_ctx, not_bst_ctx, 1), id="bst_safe_insert", marks=pytest.mark.slow),
    pytest.param(Triple("avl_safe_find", avl_ctx, not_avl_ctx, 0), id="avl_safe_find", marks=pytest.mark.slow),
]

pytestmark = pytest.mark.skipif(shutil.which("golem", path=str(SOLVERS)) is None, reason="golem executable not found")


@pytest.fixture(autouse=True)
def fresh_smt_environment() -> None:
    """Labels are interned across programs, so the same predicate name can have a different signature in two
    programs: every test declares its predicates in a new pySMT environment."""
    reset_env()


def solve(system: CHCSystem) -> Status:
    solver = GolemSolver(binary_path=SOLVERS)
    solver.load_system(system)
    return solver.solve(timeout=TIMEOUT)


@pytest.mark.parametrize("triple", TRIPLES)
def test_memory_safety_and_bounds_under_precondition(triple: Triple) -> None:
    function = parse_file(str(C_FILES / f"{triple.program}.c"))
    system = pre.make_system(function, function.node.k, triple.m, N, triple.pre(), ALL_EXITS)
    assert solve(system) == Status.SAT


@pytest.mark.parametrize("triple", TRIPLES)
def test_postcondition_under_precondition(triple: Triple) -> None:
    function = parse_file(str(C_FILES / f"{triple.program}.c"))
    system = post.make_system(function, function.node.k, triple.m, N, N_DFS, triple.post(), pre=triple.pre())
    assert solve(system) == Status.SAT


def test_postcondition_needs_the_precondition() -> None:
    """Inserting into an unsorted list does not produce a sorted list."""
    function = parse_file(str(C_FILES / "sll_safe_insert_sorted.c"))
    system = post.make_system(function, function.node.k, 1, N, N_DFS, not_sll_sorted_ctx())
    assert solve(system) == Status.UNSAT


def test_insert_breaks_strict_bst() -> None:
    """Inserting a key already in a strict BST produces a duplicate: the strict postcondition is violated."""
    function = parse_file(str(C_FILES / "bst_safe_insert.c"))
    system = post.make_system(function, function.node.k, 1, N, N_DFS, not_bst_strict_ctx(), pre=bst_strict_ctx())
    assert solve(system) == Status.UNSAT


def test_avl_safe_insert_is_accepted_by_the_parser() -> None:
    """Iterative AVL insertion (Knuth's Algorithm A with heights), in the subset accepted by the parser."""
    function = parse_file(str(C_FILES / "avl_safe_insert.c"))
    assert function.name == "avl_safe_insert"
    assert [f.name for f in function.node.pointer_fields] == ["left", "right"]
    assert [f.name for f in function.node.data_fields] == ["data", "height"]


@pytest.mark.slow
def test_avl_safe_insert_memory_safety_under_precondition() -> None:
    """No null-pointer dereference on AVL inputs within the bound n."""
    function = parse_file(str(C_FILES / "avl_safe_insert.c"))
    system = pre.make_system(function, function.node.k, 1, N, avl_ctx(), frozenset({ExitCodeKind.ERR}))
    assert solve(system) == Status.SAT


@pytest.mark.slow
def test_avl_safe_insert_postcondition_under_precondition() -> None:
    """Every execution on an AVL input ending at `exit` within the bound n produces an AVL tree.

    Unlike the triples above the bound is not checked: executions that overflow are not covered."""
    function = parse_file(str(C_FILES / "avl_safe_insert.c"))
    system = post.make_system(function, function.node.k, 1, N, N_DFS, not_avl_ctx(), pre=avl_ctx())
    assert solve(system) == Status.SAT
