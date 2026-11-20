"""psi_rb and not_psi_rb_struct against a reference red-black check, on every shape and colouring with up to 5
nodes."""

import itertools
from typing import Any, Callable, Iterator

import pytest
import z3  # pyright: ignore[reportMissingTypeStubs]

from treehornx import smt as sx
from treehornx.analysis.constraints.sdta.psi import not_psi_rb_struct, psi_rb, rb_struct_error_psiF, root_is_black
from treehornx.analysis.constraints.sdta.SDTAContext import (
    SDTAContext,
    not_rb_black_height_ctx,
    not_rb_red_ctx,
    not_rb_root_black_ctx,
)


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
) -> tuple[list[sx.SExpr], dict[str, sx.SExpr] | None]:
    """Constraints of the automaton run on `tree` and the state of its root."""
    if tree is None:
        return [], None
    left_constraints, left_state = run_psi(tree[0], red, key, counter)
    right_constraints, right_state = run_psi(tree[1], red, key, counter)
    i = next(counter)
    state: dict[str, sx.SExpr] = {
        "min": sx.Var.make(name=f"min{i}", type=sx.Type.Int),
        "max": sx.Var.make(name=f"max{i}", type=sx.Type.Int),
        "data": sx.Var.make(name=f"data{i}", type=sx.Type.Int),
        "black_height": sx.Var.make(name=f"black_height{i}", type=sx.Type.Int),
        "red": sx.Var.make(name=f"red{i}", type=sx.Type.Bool),
    }
    fields: dict[str, sx.SExpr] = {
        "data": sx.Constant.make(value=key[id(tree)]),
        "red": sx.Constant.make(value=red[id(tree)]),
    }
    psi = psi_rb({"left": left_state, "right": right_state}, fields, state)
    return [*left_constraints, *right_constraints, psi], state


def is_sat(formula: sx.SExpr) -> bool:
    declarations = "".join(f"(declare-const {v.name} {v.type.value})" for v in set(formula.free_variables()))
    solver: Any = z3.Solver()
    solver.from_string(f"{declarations}(assert {formula.to_smt()})")
    return bool(solver.check() == z3.sat)


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
    assert is_sat(sx.OpExpr.make(op=sx.Operator.AND, args=(*constraints, root_is_black(root)))) == expected


def run_not_psi_struct(
    tree: Tree, red: dict[int, bool], counter: Iterator[int]
) -> tuple[list[sx.SExpr], dict[str, sx.SExpr] | None]:
    """Constraints of the run of not_psi_rb_struct on `tree` and the state of its root. The data are decreasing in
    order (not a BST): the automaton must not read them."""
    if tree is None:
        return [], None
    left_constraints, left_state = run_not_psi_struct(tree[0], red, counter)
    right_constraints, right_state = run_not_psi_struct(tree[1], red, counter)
    i = next(counter)
    state: dict[str, sx.SExpr] = {
        "black_height": sx.Var.make(name=f"black_height{i}", type=sx.Type.Int),
        "red": sx.Var.make(name=f"red{i}", type=sx.Type.Bool),
        "error": sx.Var.make(name=f"error{i}", type=sx.Type.Bool),
    }
    fields: dict[str, sx.SExpr] = {"data": sx.Constant.make(value=-i), "red": sx.Constant.make(value=red[id(tree)])}
    psi = not_psi_rb_struct({"left": left_state, "right": right_state}, fields, state)
    return [*left_constraints, *right_constraints, psi], state


@pytest.mark.parametrize(("tree", "colours"), list(cases()))
def test_not_psi_rb_struct_matches_reference(tree: Tree, colours: tuple[bool, ...]) -> None:
    """The run is total and deterministic: the error is reachable iff the tree breaks the red-black structure."""
    nodes = in_order(tree)
    red = {id(node): colour for node, colour in zip(nodes, colours, strict=True)}
    constraints, root = run_not_psi_struct(tree, red, itertools.count())
    assert root is not None
    is_rb = black_height(tree, red) is not None and not red[id(tree)]
    run = sx.OpExpr.make(op=sx.Operator.AND, args=constraints)
    assert is_sat(run)
    assert is_sat(sx.OpExpr.make(op=sx.Operator.AND, args=(run, rb_struct_error_psiF(root)))) == (not is_rb)
    assert (
        is_sat(
            sx.OpExpr.make(
                op=sx.Operator.AND, args=(run, sx.OpExpr.make(op=sx.Operator.NOT, args=(rb_struct_error_psiF(root),)))
            )
        )
        == is_rb
    )


def red_rule(tree: Tree, red: dict[int, bool]) -> bool:
    """Reference: no red node has a red child."""
    if tree is None:
        return True
    if red[id(tree)] and any(child is not None and red[id(child)] for child in tree):
        return False
    return red_rule(tree[0], red) and red_rule(tree[1], red)


def heights(tree: Tree, red: dict[int, bool]) -> set[int]:
    """Reference: the numbers of black nodes on the paths from `tree` down to nil."""
    if tree is None:
        return {0}
    own = 0 if red[id(tree)] else 1
    return {own + h for child in tree for h in heights(child, red)}


def same_black_height(tree: Tree, red: dict[int, bool]) -> bool:
    """Reference: every subtree has a single black height."""
    if tree is None:
        return True
    return len(heights(tree, red)) == 1 and same_black_height(tree[0], red) and same_black_height(tree[1], red)


def black_root(tree: Tree, red: dict[int, bool]) -> bool:
    """Reference: the root is black."""
    return tree is None or not red[id(tree)]


RB_PARTS = [
    pytest.param(not_rb_red_ctx, red_rule, id="rb_red"),
    pytest.param(not_rb_black_height_ctx, same_black_height, id="rb_black_height"),
    pytest.param(not_rb_root_black_ctx, black_root, id="rb_root_black"),
]


def run_ctx(
    ctx: SDTAContext, tree: Tree, red: dict[int, bool], counter: Iterator[int]
) -> tuple[list[sx.SExpr], dict[str, sx.SExpr] | None]:
    """Constraints of the run of `ctx` on `tree` and the state of its root, data decreasing in order (not a BST)."""
    if tree is None:
        return [], None
    left_constraints, left_state = run_ctx(ctx, tree[0], red, counter)
    right_constraints, right_state = run_ctx(ctx, tree[1], red, counter)
    i = next(counter)
    state: dict[str, sx.SExpr] = {
        name: sx.Var.make(name=f"{name}{i}", type=sx.Type.Int if kind == "int" else sx.Type.Bool)
        for name, kind in ctx.states.items()
    }
    fields: dict[str, sx.SExpr] = {"data": sx.Constant.make(value=-i), "red": sx.Constant.make(value=red[id(tree)])}
    psi = ctx.psi({"left": left_state, "right": right_state}, fields, state)
    return [*left_constraints, *right_constraints, psi], state


@pytest.mark.parametrize(("make_ctx", "holds"), RB_PARTS)
@pytest.mark.parametrize(("tree", "colours"), list(cases()))
def test_negated_rb_parts_match_reference(
    make_ctx: Callable[[], SDTAContext],
    holds: Callable[[Tree, dict[int, bool]], bool],
    tree: Tree,
    colours: tuple[bool, ...],
) -> None:
    """Each negated automaton has a run on every tree, and ψ_F holds at the root iff its property fails."""
    nodes = in_order(tree)
    red = {id(node): colour for node, colour in zip(nodes, colours, strict=True)}
    ctx = make_ctx()
    constraints, root = run_ctx(ctx, tree, red, itertools.count())
    assert root is not None
    run = sx.OpExpr.make(op=sx.Operator.AND, args=constraints)
    assert is_sat(run)
    assert is_sat(sx.OpExpr.make(op=sx.Operator.AND, args=(run, ctx.psiF(root)))) == (not holds(tree, red))
    assert is_sat(
        sx.OpExpr.make(op=sx.Operator.AND, args=(run, sx.OpExpr.make(op=sx.Operator.NOT, args=(ctx.psiF(root),))))
    ) == holds(tree, red)
