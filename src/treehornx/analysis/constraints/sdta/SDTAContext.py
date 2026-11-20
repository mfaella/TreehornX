from dataclasses import dataclass
from typing import Literal

from loguru import logger

from treehornx.analysis.constraints.sdta.psi import (
    PsiFType,
    PsiType,
    error_psiF,
    not_psi_avl,
    not_psi_avl_h,
    not_psi_avl_struct,
    not_psi_bst,
    not_psi_bst_strict,
    not_psi_rb,
    not_psi_rb_black_height,
    not_psi_rb_red,
    not_psi_rb_root_black,
    not_psi_rb_struct,
    not_psi_rb_struct_height,
    not_psi_sll_sorted,
    not_psi_sll_sorted_strict,
    psi_avl,
    psi_avl_h,
    psi_bst,
    psi_bst_strict,
    psi_rb,
    psi_rb_struct,
    psi_sll_sorted,
    psi_sll_sorted_strict,
    psi_true,
    psiF_empty,
    psiF_false,
    rb_struct_error_psiF,
    root_is_black_psiF,
    root_is_red_psiF,
)


@dataclass(slots=True, frozen=True)
class SDTAContext:
    psi: PsiType
    psiF: PsiFType
    states: dict[str, Literal["int", "bool"]]


def bst_ctx() -> SDTAContext:
    logger.debug("Creating BST context")
    psi, psiF = psi_bst, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int"}
    return SDTAContext(psi, psiF, states)


def not_bst_ctx() -> SDTAContext:
    logger.debug("Creating not-BST context")
    psi, psiF = not_psi_bst, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def bst_strict_ctx() -> SDTAContext:
    logger.debug("Creating BST strict context")
    psi, psiF = psi_bst_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int"}
    return SDTAContext(psi, psiF, states)


def not_bst_strict_ctx() -> SDTAContext:
    logger.debug("Creating not-BST strict context")
    psi, psiF = not_psi_bst_strict, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def sll_sorted_ctx() -> SDTAContext:
    logger.debug("Creating SLL sorted context")
    psi, psiF = psi_sll_sorted, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int"}
    return SDTAContext(psi, psiF, states)


def not_sll_sorted_ctx() -> SDTAContext:
    logger.debug("Creating not-SLL sorted context")
    psi, psiF = not_psi_sll_sorted, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def sll_sorted_strict_ctx() -> SDTAContext:
    logger.debug("Creating SLL sorted strict context")
    psi, psiF = psi_sll_sorted_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int"}
    return SDTAContext(psi, psiF, states)


def not_sll_sorted_strict_ctx() -> SDTAContext:
    logger.debug("Creating not-SLL sorted strict context")
    psi, psiF = not_psi_sll_sorted_strict, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def avl_ctx() -> SDTAContext:
    logger.debug("Creating AVL context")
    psi, psiF = psi_avl, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
    return SDTAContext(psi, psiF, states)


def not_avl_ctx() -> SDTAContext:
    logger.debug("Creating not-AVL context")
    psi, psiF = not_psi_avl, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {
        "min": "int",
        "max": "int",
        "data": "int",
        "height": "int",
        "error": "bool",
    }
    return SDTAContext(psi, psiF, states)


def avl_h_ctx() -> SDTAContext:
    """`avl_ctx` for nodes with a `height` field in place of the `bal` field."""
    logger.debug("Creating AVL (height) context")
    psi, psiF = psi_avl_h, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
    return SDTAContext(psi, psiF, states)


def not_avl_h_ctx() -> SDTAContext:
    """The negation of `avl_h_ctx`."""
    logger.debug("Creating not-AVL (height) context")
    psi, psiF = not_psi_avl_h, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {
        "min": "int",
        "max": "int",
        "data": "int",
        "height": "int",
        "error": "bool",
    }
    return SDTAContext(psi, psiF, states)


def rb_ctx() -> SDTAContext:
    psi, psiF = psi_rb, root_is_black_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {
        "min": "int",
        "max": "int",
        "data": "int",
        "black_height": "int",
        "red": "bool",
    }
    return SDTAContext(psi, psiF, states)


def not_rb_ctx() -> SDTAContext:
    """The negation of `rb_ctx`: the tree breaks the strict bst order or the red-black structure, or has a red
    root."""
    logger.debug("Creating not-RB context")
    psi, psiF = not_psi_rb, rb_struct_error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {
        "min": "int",
        "max": "int",
        "data": "int",
        "black_height": "int",
        "red": "bool",
        "error": "bool",
    }
    return SDTAContext(psi, psiF, states)


def rb_struct_ctx() -> SDTAContext:
    """`rb_ctx` without the bst check: the tree has the red-black structure (same black height on every path, no
    red node with a red child, black root)."""
    logger.debug("Creating RB structure context")
    psi, psiF = psi_rb_struct, root_is_black_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"black_height": "int", "red": "bool"}
    return SDTAContext(psi, psiF, states)


def not_rb_struct_ctx() -> SDTAContext:
    """The negation of `rb_ctx` without the bst check: the tree breaks the red-black structure (same black height
    on every path, no red node with a red child, black root)."""
    logger.debug("Creating not-RB structure context")
    psi, psiF = not_psi_rb_struct, rb_struct_error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"black_height": "int", "red": "bool", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def not_rb_red_ctx() -> SDTAContext:
    """The negation of "a red node has only black children"."""
    logger.debug("Creating not-RB red context")
    psi, psiF = not_psi_rb_red, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"red": "bool", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def not_rb_black_height_ctx() -> SDTAContext:
    """The negation of "every path down to nil has the same number of black nodes"."""
    logger.debug("Creating not-RB black height context")
    psi, psiF = not_psi_rb_black_height, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"black_height": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def not_rb_root_black_ctx() -> SDTAContext:
    """The negation of "the root is black"."""
    logger.debug("Creating not-RB root black context")
    psi, psiF = not_psi_rb_root_black, root_is_red_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"red": "bool"}
    return SDTAContext(psi, psiF, states)


def not_avl_struct_ctx() -> SDTAContext:
    """The negation of `avl_ctx` without the bst check: some `bal` field is not height(right) - height(left) or is
    outside {-1, 0, 1}."""
    logger.debug("Creating not-AVL structure context")
    psi, psiF = not_psi_avl_struct, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"height": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def not_rb_struct_height_ctx() -> SDTAContext:
    """`not_rb_struct_ctx` with a height check in place of the black-height check: some red node has a red child,
    some node has a subtree more than twice as high as the other, or the root is red."""
    logger.debug("Creating not-RB structure (height) context")
    psi, psiF = not_psi_rb_struct_height, rb_struct_error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"height": "int", "red": "bool", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def true_ctx() -> SDTAContext:
    """The automaton accepting every tree, with no state: memory safety without a precondition."""
    return SDTAContext(psi_true, psiF_empty, {})


def dummy_pre_ctx() -> SDTAContext:
    """The precondition of a run without `--pre`: it accepts every input tree, the empty tree included. It has no
    state, so it adds no symbol to the labels, and its constraints are true."""
    return true_ctx()


def dummy_post_ctx() -> SDTAContext:
    """The negated postcondition A¬post of a run without `--post`: it accepts no output tree, so the postcondition
    error is never reachable. It has no state, so it adds no symbol to the labels; ψ is true and ψ_F is false."""
    return SDTAContext(psi_true, psiF_false, {})
