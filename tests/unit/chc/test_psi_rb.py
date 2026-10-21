"""psi_rb against a reference red-black check, on every shape and colouring with up to 5 nodes."""

import itertools
from typing import Iterator

import pysmt.shortcuts as smt
import pytest
from pysmt.fnode import FNode
from pysmt.typing import INT

from treehornx.chc.sdta.psi import psi_rb, root_is_black


# a tree is None (nil) or the pair (left, right)
Tree = tuple["Tree", "Tree"] | None


def shapes(n: int) -> Iterator[Tree]:
    if n == 0:
        yield None
        return
    for left_size in range(n):
        for left in shapes(left_size):
            for right in shapes(n - 1 - left_size):
                yield (left, right)


def in_order(tree: Tree) -> list[tuple[Tree, Tree]]:
    if tree is None:
        return []
    return [*in_order(tree[0]), tree, *in_order(tree[1])]


def black_height(tree: Tree, red: dict[int, bool]) -> int | None:
    """Reference check: the black height of `tree`, None if it breaks a red-black property."""
    if tree is None:
        return 0
    left, right = black_height(tree[0], red), black_height(tree[1], red)
    if left is None or left != right:
        return None
    if red[id(tree)] and any(child is not None and red[id(child)] for child in tree):
        return None
    return left + (0 if red[id(tree)] else 1)


def run_psi(
    tree: Tree, red: dict[int, bool], key: dict[int, int], counter: Iterator[int]
) -> tuple[list[FNode], dict[str, FNode] | None]:
    """Constraints of the automaton run on `tree` and the state of its root."""
    if tree is None:
        return [], None
    left_constraints, left_state = run_psi(tree[0], red, key, counter)
    right_constraints, right_state = run_psi(tree[1], red, key, counter)
    i = next(counter)
    state = {
        "min": smt.Symbol(f"min{i}", INT),
        "max": smt.Symbol(f"max{i}", INT),
        "data": smt.Symbol(f"data{i}", INT),
        "black_height": smt.Symbol(f"black_height{i}", INT),
        "red": smt.Symbol(f"red{i}"),
    }
    fields = {"data": smt.Int(key[id(tree)]), "red": smt.Bool(red[id(tree)])}
    psi = psi_rb({"left": left_state, "right": right_state}, fields, state)
    return [*left_constraints, *right_constraints, psi], state


def cases() -> Iterator[tuple[Tree, tuple[bool, ...]]]:
    for n in range(1, 6):
        for tree in shapes(n):
            for colours in itertools.product((False, True), repeat=n):
                yield tree, colours


@pytest.mark.parametrize(("tree", "colours"), list(cases()))
def test_psi_rb_matches_reference(tree: Tree, colours: tuple[bool, ...]) -> None:
    nodes = in_order(tree)
    red = {id(node): colour for node, colour in zip(nodes, colours, strict=True)}
    key = {id(node): 10 * i for i, node in enumerate(nodes)}  # increasing in order: a strict BST
    constraints, root = run_psi(tree, red, key, itertools.count())
    assert root is not None
    expected = black_height(tree, red) is not None and not red[id(tree)]
    assert smt.is_sat(smt.And(*constraints, root_is_black(root))) == expected
