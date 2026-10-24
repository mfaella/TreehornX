"""Every tree-shape check fires on the program built to violate it, and none fires on programs keeping a tree."""

from pathlib import Path

import pytest

from treehornx.chc import Post
from treehornx.enum_models.Taint.shape import ShapeError, label_errors, pair_errors
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24


def shape_errors(program: str, m: int) -> set[ShapeError]:
    function = parse_file(str(C_FILES / f"{program}.c"))
    post = Post.build_post(function, function.node.k, m, N)
    errors = {e for label in post.labels for e in label_errors(post.engine, label)}
    return errors | {e for pair in post.pairs for e in pair_errors(post.engine, pair)}


@pytest.mark.parametrize(
    ("program", "m", "expected"),
    [
        ("sll_unsafe_circular", 0, {ShapeError.ROOT_SEED_ON_FIELD_SEED, ShapeError.SELF_LOOP}),
        ("bst_unsafe_post_1", 0, {ShapeError.STRUCTURAL_AND_POINTER}),
        ("bst_unsafe_shape_two_fields", 1, {ShapeError.TRAILS_MERGE}),
        ("bst_unsafe_shape_two_nodes", 1, {ShapeError.TRAILS_MERGE}),
        ("bst_unsafe_shape_seed", 1, {ShapeError.TRAIL_ON_SEED}),
        ("bst_unsafe_shape_free_child", 0, {ShapeError.DANGLING_STRUCTURAL_CHILD}),
        ("bst_unsafe_shape_free_moved", 0, {ShapeError.DANGLING_POINTER_CHILD}),
        ("bst_safe_shape_swap", 0, set[ShapeError]()),
        ("sll_post_set_zero", 0, set[ShapeError]()),
        ("sll_safe_reverse", 0, set[ShapeError]()),
    ],
)
def test_shape_errors(program: str, m: int, expected: set[ShapeError]) -> None:
    assert shape_errors(program, m) == expected
