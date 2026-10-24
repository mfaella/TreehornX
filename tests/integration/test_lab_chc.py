"""Memory safety of tree-manipulating programs without a precondition.

The automaton accepting every tree runs bottom-up over the backbone and the root's query fires when some
node of the tree ends with a null-pointer dereference: the system is sat when no such tree exists (the
program is safe within the bounds m, n) and unsat otherwise.
"""

import pytest

from treehornx.chc.solvers import Status

from .config import TestConfig, params, run


SAT, UNSAT = Status.SAT, Status.UNSAT

CONFIGS = (
    TestConfig("sll_safe_find", SAT),
    TestConfig("sll_unsafe_find", UNSAT),
    TestConfig("sll_safe_insert_sorted", SAT, m=1),
    TestConfig("sll_unsafe_insert", UNSAT, m=1),
    TestConfig("sll_safe_length", SAT),
    TestConfig("sll_unsafe_length", UNSAT),
    TestConfig("sll_safe_find_last", SAT, solver="eldarica"),
    TestConfig("sll_unsafe_find_last", UNSAT),
    TestConfig("bst_safe_find", SAT),
    TestConfig("bst_unsafe_find", UNSAT),
    TestConfig("bst_safe_insert", SAT, m=1),
    TestConfig("bst_unsafe_insert", UNSAT, m=1),
    # fields compared with NULL directly (if p->pf == NULL), without loading them into a variable
    TestConfig("bst_safe_min_field_nil", SAT),
    TestConfig("bst_unsafe_min_field_nil", UNSAT),
    TestConfig("bst_safe_insert_field_nil", SAT, m=1),
    TestConfig("bst_safe_insert_load", SAT, m=1, solver="eldarica"),
    # a field compared with NULL assigned to a variable (b = p->pf == NULL)
    TestConfig("bst_safe_assign_field_nil", SAT),
    TestConfig("bst_unsafe_assign_field_nil", UNSAT),
    # a new node linked by its parent and reached again through the field: its frame Here(q) is entered from
    # the parent and leaves to it
    TestConfig("bst_unsafe_linked_new", UNSAT, m=1),
)
CASES = params(*CONFIGS)


@pytest.mark.parametrize("config", CASES)
def test_memory_safety(config: TestConfig) -> None:
    assert run(config) == config.expected
