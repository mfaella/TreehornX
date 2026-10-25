"""Tree shape of the output heap (POPL27, Sec. 6): the system over the tainted labels is unsat iff some input leads
to an output reachable from the root that is not a tree. Every program here is memory safe (checked by
`test_memory_safe`), so the violations come from the tree-shape errors alone."""

import pytest

from treehornx.chc import TreeShape
from treehornx.chc.solvers import Status
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.enum_models.Taint import BoolPlus
from treehornx.parser import parse_file

from .config import C_FILES, TestConfig, params, run


SAT, UNSAT = Status.SAT, Status.UNSAT

SAFE = (
    TestConfig("sll_safe_shape_set_zero", SAT),
    TestConfig("sll_safe_reverse", SAT),
    # the output starts at the second node
    TestConfig("sll_safe_shape_drop_head", SAT),
    # increments every data field
    TestConfig("sll_safe_shape_increment", SAT),
    # inserts a new node after the head
    TestConfig("sll_safe_shape_insert_second", SAT, m=1),
    # reverses the prefix of nodes with data <= key, then reattaches the rest
    TestConfig("sll_safe_shape_partial_reverse", SAT),
    # reverses the first two nodes with a counter, then reattaches the rest
    TestConfig("sll_safe_shape_partial_reverse_two", SAT),
    # appends a new node
    TestConfig("sll_safe_shape_push_back", SAT, m=1),
    # inserts a new head
    TestConfig("sll_safe_shape_push_front", SAT, m=1),
    # removes and frees the head
    TestConfig("sll_safe_shape_remove_head", SAT),
    # removes the first node with data == key
    TestConfig("sll_safe_shape_remove_key", SAT),
    # unlinks and frees the second node
    TestConfig("sll_safe_shape_remove_second", SAT),
    # complete reverse
    TestConfig("sll_safe_shape_reverse", SAT),
    # moves the head to the tail
    TestConfig("sll_safe_shape_rotate", SAT),
    # cuts the list after the first node with data > key
    TestConfig("sll_safe_shape_split", SAT),
    # swaps the first two nodes
    TestConfig("sll_safe_shape_swap_first_two", SAT),
    # keeps only the head, freeing the rest
    TestConfig("sll_safe_shape_truncate", SAT),
    # drops the right subtree
    TestConfig("bst_safe_shape_cut_right", SAT),
    # moves the right subtree under the left child, when its right field is free
    TestConfig("bst_safe_shape_graft", SAT),
    # swaps the children of the left child
    TestConfig("bst_safe_shape_mirror_left", SAT),
    # a new root with the old one as left child
    TestConfig("bst_safe_shape_new_root", SAT, m=1),
    # a new node between the root and its left child
    TestConfig("bst_safe_shape_push_down_left", SAT, m=1),
    # removes the leftmost node, its right subtree takes its place
    TestConfig("bst_safe_shape_remove_min", SAT),
    # left rotation at the root
    TestConfig("bst_safe_shape_rotate_left", SAT),
    # right rotation at the root
    TestConfig("bst_safe_shape_rotate_right", SAT),
    # swaps the children of the root: still a tree
    TestConfig("bst_safe_shape_swap", SAT),
)

UNSAFE = (
    TestConfig("sll_unsafe_circular", UNSAT),
    # root->left == root->right
    TestConfig("bst_unsafe_shape_share_children", UNSAT),
    # leftmost->left = root
    TestConfig("bst_unsafe_shape_leftmost_to_root", UNSAT),
    # the second node points back to the head
    TestConfig("sll_unsafe_shape_back_edge", UNSAT),
    # skips the second node, then frees the third instead of the second
    TestConfig("sll_unsafe_shape_free_relinked", UNSAT),
    # frees the second node without unlinking it
    TestConfig("sll_unsafe_shape_free_second_linked", UNSAT),
    # frees the tail without unlinking it
    TestConfig("sll_unsafe_shape_free_tail", UNSAT),
    # a new second node, also pointed to by the third
    TestConfig("sll_unsafe_shape_new_shared", UNSAT, m=1),
    # partial reverse reattaching the new head instead of the rest
    TestConfig("sll_unsafe_shape_partial_reverse_back_edge", UNSAT),
    # partial reverse starting with y = root
    TestConfig("sll_unsafe_shape_partial_reverse_from_head", UNSAT),
    # reverses two nodes with a counter, reattaching the new head
    TestConfig("sll_unsafe_shape_partial_reverse_two_back_edge", UNSAT),
    # the new node is both the head and after the tail
    TestConfig("sll_unsafe_shape_push_front_and_back", UNSAT, m=1),
    # complete reverse, then the old head points to the new one
    TestConfig("sll_unsafe_shape_reverse_back_edge", UNSAT),
    # complete reverse starting with y = root: the old head keeps its next
    TestConfig("sll_unsafe_shape_reverse_from_head", UNSAT),
    # moves the head to the tail without cutting its next
    TestConfig("sll_unsafe_shape_rotate_no_cut", UNSAT),
    # the head points to itself
    TestConfig("sll_unsafe_shape_self_loop", UNSAT),
    # swaps the first two nodes forgetting to relink the first
    TestConfig("sll_unsafe_shape_swap_no_fix", UNSAT),
    # the tail points to the second node
    TestConfig("sll_unsafe_shape_tail_to_second", UNSAT),
    # the left child points back to the root
    TestConfig("bst_unsafe_shape_child_to_parent", UNSAT),
    # root->left is freed but still linked
    TestConfig("bst_unsafe_shape_free_child", UNSAT),
    # frees the left grandchild without unlinking it
    TestConfig("bst_unsafe_shape_free_grandchild", UNSAT),
    # root->left is moved to root->right, then freed
    TestConfig("bst_unsafe_shape_free_moved", UNSAT),
    # the left subtree is also grafted under the right child
    TestConfig("bst_unsafe_shape_graft_no_cut", UNSAT),
    # the left grandchild points back to the root
    TestConfig("bst_unsafe_shape_grandchild_to_root", UNSAT),
    # a new root that is also the right child of the old one
    TestConfig("bst_unsafe_shape_new_root_cycle", UNSAT, m=1),
    # frees the leftmost node keeping the link to it
    TestConfig("bst_unsafe_shape_remove_min_keep", UNSAT),
    # both fields of the root point to the right child
    TestConfig("bst_unsafe_shape_right_twice", UNSAT),
    # left rotation forgetting root->right := r->left
    TestConfig("bst_unsafe_shape_rotate_left_no_cut", UNSAT),
    # right rotation forgetting root->left := l->right
    TestConfig("bst_unsafe_shape_rotate_right_no_cut", UNSAT),
    # root->right and root->left->left both point to the new node; the lace goes down from the update of root->right
    TestConfig("bst_unsafe_shape_seed", UNSAT, m=1),
    # the root is its own right child
    TestConfig("bst_unsafe_shape_self_loop", UNSAT),
    # the left grandchild is also the right child of the left child
    TestConfig("bst_unsafe_shape_share_grandchild", UNSAT),
    # root->left and root->right both point to the new node
    TestConfig("bst_unsafe_shape_two_fields", UNSAT, m=1),
    # root->right and root->left->left both point to the new node
    TestConfig("bst_unsafe_shape_two_nodes", UNSAT, m=1),
)

SHAPES = (*SAFE, *UNSAFE)
CASES = params(*(TestConfig(c.program, c.expected, m=c.m, layer="tree_shape", id=f"{c.program}-shape") for c in SHAPES))
MEMORY_SAFE = params(*(TestConfig(c.program, SAT, m=c.m, id=f"{c.program}-memory") for c in SHAPES))


@pytest.mark.parametrize("config", MEMORY_SAFE)
def test_memory_safe(config: TestConfig) -> None:
    assert run(config) == config.expected


@pytest.mark.parametrize("config", CASES)
def test_tree_shape(config: TestConfig) -> None:
    assert run(config) == config.expected


@pytest.mark.parametrize("config", SAFE, ids=[c.program for c in SAFE])
def test_safe_outputs_are_reconstructed(config: TestConfig) -> None:
    """A safe verdict is not vacuous: some final root is queried and some output root is tainted ⊤+."""
    function = parse_file(str(C_FILES / f"{config.program}.c"))
    shape = TreeShape.build_tree_shape(function, function.node.k, config.m, config.n)
    assert any(is_initial(label.lab) for label in shape.labels)
    assert any(label.taint_node is BoolPlus.TopPlus for label in shape.labels)


def test_case_counts() -> None:
    assert len(SAFE) >= 20 and len(UNSAFE) >= 20
