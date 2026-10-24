"""Tree shape under a precondition: the shape errors fire only on the inputs accepted by the precondition. Every
program is memory safe under the same precondition, and each pre_shape program builds a non-tree exactly when its
input violates (or satisfies, for the unsafe ones) the order the precondition imposes."""

import pytest

from treehornx.chc.solvers import Status
from treehornx.main import PreType

from .config import TestConfig, params, run


SAT, UNSAT = Status.SAT, Status.UNSAT

# program, m, {precondition: tree-shape verdict}
EXPECTED: tuple[tuple[str, int, dict[PreType | None, Status]], ...] = (
    # cycle when the left child is greater than the root
    ("bst_pre_shape_left_greater", 0, {None: UNSAT, "bst": SAT, "bst_strict": SAT}),
    # cycle when the right child is smaller than the root
    ("bst_pre_shape_right_smaller", 0, {None: UNSAT, "bst": SAT, "bst_strict": SAT}),
    # cycle when the left child equals the root: allowed by bst, not by bst_strict
    ("bst_pre_shape_left_equal", 0, {None: UNSAT, "bst": UNSAT, "bst_strict": SAT}),
    # cycle when the left child is smaller than the root: allowed by every bst
    ("bst_pre_shape_left_smaller", 0, {None: UNSAT, "bst": UNSAT, "bst_strict": UNSAT}),
    # cycle when the leftmost node is greater than the root
    ("bst_pre_shape_min_greater", 0, {None: UNSAT, "bst": SAT}),
    # the right child shared under the left one when they are out of order
    ("bst_pre_shape_share_if_unordered", 0, {None: UNSAT, "bst": SAT}),
    # back edge when the second node is smaller than the head
    ("sll_pre_shape_back_edge_if_unsorted", 0, {None: UNSAT, "sll_sorted": SAT, "sll_sorted_strict": SAT}),
    # back edge when the second node is not smaller than the head: allowed by sll_sorted
    ("sll_pre_shape_back_edge_if_sorted", 0, {None: UNSAT, "sll_sorted": UNSAT}),
    # back edge to the head at the first descent along the list
    ("sll_pre_shape_cycle_on_descent", 0, {None: UNSAT, "sll_sorted": SAT}),
    # the second node freed but still linked when it is smaller than the head
    ("sll_pre_shape_free_if_unsorted", 0, {None: UNSAT, "sll_sorted": SAT}),
    # a precondition does not change the verdict of programs that do not depend on the data
    ("bst_safe_shape_rotate_right", 0, {"bst": SAT}),
    ("bst_safe_shape_remove_min", 0, {"bst": SAT}),
    ("bst_safe_insert", 1, {"bst": SAT}),
    ("bst_unsafe_shape_child_to_parent", 0, {"bst": UNSAT}),
    ("bst_unsafe_shape_right_twice", 0, {"bst": UNSAT}),
    ("sll_safe_shape_reverse", 0, {"sll_sorted": SAT}),
    ("sll_safe_shape_partial_reverse", 0, {"sll_sorted": SAT}),
    ("sll_safe_insert_sorted", 1, {"sll_sorted": SAT}),
    ("sll_unsafe_shape_reverse_back_edge", 0, {"sll_sorted": UNSAT}),
    ("sll_unsafe_shape_partial_reverse_back_edge", 0, {"sll_sorted": UNSAT}),
)


def _id(program: str, pre: PreType | None, check: str) -> str:
    return f"{program}-{pre or 'nopre'}-{check}"


CASES = params(
    *(
        TestConfig(program, expected, m=m, pre=pre, layer="post", id=_id(program, pre, "shape"))
        for program, m, verdicts in EXPECTED
        for pre, expected in verdicts.items()
    )
)
MEMORY_SAFE = params(
    *(
        TestConfig(program, SAT, m=m, pre=pre, id=_id(program, pre, "memory"))
        for program, m, verdicts in EXPECTED
        for pre in verdicts
    )
)


@pytest.mark.parametrize("config", MEMORY_SAFE)
def test_memory_safe_under_precondition(config: TestConfig) -> None:
    assert run(config) == config.expected


@pytest.mark.parametrize("config", CASES)
def test_tree_shape_under_precondition(config: TestConfig) -> None:
    assert run(config) == config.expected
