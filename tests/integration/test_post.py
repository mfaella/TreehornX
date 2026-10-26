"""Postcondition: the negated postcondition automaton runs on the output tree, under the precondition if given. Every
program is memory safe and builds a tree (checked by `test_tree_shape.py` and `test_tree_shape_pre.py`)."""

import pytest

from treehornx.chc.solvers import Status
from treehornx.main import PostType, PreType

from .config import TestConfig, params, run


SAT, UNSAT = Status.SAT, Status.UNSAT

# program, m, precondition, postcondition, verdict
EXPECTED: tuple[tuple[str, int, PreType | None, PostType, Status], ...] = (
    # a sorted insertion keeps the list sorted, an unsorted input is not sorted after it
    ("sll_safe_insert_sorted", 1, "sll_sorted", "sll_sorted", SAT),
    ("sll_safe_insert_sorted", 1, None, "sll_sorted", UNSAT),
    # the reverse of a list of two different values is not sorted
    ("sll_safe_shape_reverse", 0, None, "sll_sorted", UNSAT),
    ("sll_safe_shape_reverse", 0, "sll_sorted_strict", "sll_sorted", UNSAT),
    # a list of zeros is sorted, but not strictly when it has two nodes
    ("sll_safe_shape_set_zero", 0, None, "sll_sorted", SAT),
    ("sll_safe_shape_set_zero", 0, None, "sll_sorted_strict", UNSAT),
    # incrementing every value keeps the order
    ("sll_safe_shape_increment", 0, "sll_sorted", "sll_sorted", SAT),
    ("sll_safe_shape_increment", 0, None, "sll_sorted", UNSAT),
    # swapping the first two nodes of a strictly sorted list breaks the order
    ("sll_safe_shape_swap_first_two", 0, "sll_sorted_strict", "sll_sorted", UNSAT),
    # the insertion in a bst keeps it a bst
    ("bst_safe_insert", 1, "bst", "bst", SAT),
    ("bst_safe_insert", 1, None, "bst", UNSAT),
    # a rotation keeps the order, a mirror or a swap of the children breaks it
    ("bst_safe_shape_rotate_right", 0, "bst", "bst", SAT),
    ("bst_safe_shape_mirror_left", 0, "bst_strict", "bst", UNSAT),
    ("bst_safe_shape_swap", 0, "bst_strict", "bst", UNSAT),
)


def _id(program: str, pre: PreType | None, post: PostType) -> str:
    return f"{program}-{pre or 'nopre'}-{post}"


CASES = params(
    *(
        TestConfig(program, expected, m=m, pre=pre, post=post, layer="post", id=_id(program, pre, post))
        for program, m, pre, post, expected in EXPECTED
    )
)


@pytest.mark.parametrize("config", CASES)
def test_postcondition(config: TestConfig) -> None:
    assert run(config) == config.expected
