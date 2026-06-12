from dataclasses import dataclass
from typing import Callable, Literal

from loguru import logger

from treehornx.chc.psi import (
    PsiFType,
    PsiType,
    error_psiF,
    not_psi_avl,
    not_psi_avl_strict,
    not_psi_bst,
    not_psi_bst_strict,
    not_psi_rb_strict,
    not_psi_sll_sorted,
    not_psi_sll_sorted_strict,
    psi_avl,
    psi_avl_strict,
    psi_bst,
    psi_bst_strict,
    psi_rb,
    psi_rb_strict,
    psi_sll_sorted,
    psi_sll_sorted_strict,
    psiF_empty,
)
from treehornx.enum_labels.core.Label import Label

type LabelFilterType = Callable[[Label, bool], bool]
type PairFilterType = Callable[[tuple[Label, Label, int | str], bool], bool]

@dataclass(slots=True, frozen=True)
class SDTAContext:
    psi: PsiType
    psiF: PsiFType
    states: dict[str, Literal["int", "bool"]]
    label_filter: LabelFilterType = lambda label, is_root: True
    pair_filter: PairFilterType = lambda pair, parent_is_root: True



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
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def avl_strict_ctx() -> SDTAContext:
    logger.debug("Creating AVL strict context")
    psi, psiF = psi_avl_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
    return SDTAContext(psi, psiF, states)


def not_avl_strict_ctx() -> SDTAContext:
    logger.debug("Creating not-AVL strict context")
    psi, psiF = not_psi_avl_strict, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int", "error": "bool"}
    return SDTAContext(psi, psiF, states)


def rb_label_filter(label: Label, is_root: bool) -> bool:
    if is_root and label.frame.enum_fields["color"] == "RED":
        return False

    return True


def rb_pair_filter(pair: tuple[Label, Label, int | str], parent_is_root: bool) -> bool:
    parent, child, _ = pair
    if parent.frame.enum_fields["color"] == "RED" and child.frame.enum_fields["color"] == "RED":
        return False

    return True


def rb_ctx() -> SDTAContext:
    logger.debug("Creating Red-Black tree context")
    # Placeholder for Red-Black tree context, to be implemented
    psi, psiF = psi_rb, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "black_height": "int"}
    label_filter = rb_label_filter
    pair_filter = rb_pair_filter
    return SDTAContext(psi, psiF, states, label_filter, pair_filter)


def not_rb_ctx() -> SDTAContext:
    logger.debug("Creating not-Red-Black tree context")
    # Placeholder for Red-Black tree context, to be implemented
    psi, psiF = psi_rb, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "black_height": "int", "error": "bool"}
    label_filter = rb_label_filter
    pair_filter = rb_pair_filter
    return SDTAContext(psi, psiF, states, label_filter, pair_filter)


def rb_strict_ctx() -> SDTAContext:
    logger.debug("Creating Red-Black tree strict context")
    # Placeholder for Red-Black tree context, to be implemented
    psi, psiF = psi_rb_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "black_height": "int"}
    label_filter = rb_label_filter
    pair_filter = rb_pair_filter
    return SDTAContext(psi, psiF, states, label_filter, pair_filter)


def not_rb_strict_ctx() -> SDTAContext:
    logger.debug("Creating not-Red-Black tree strict context")
    # Placeholder for Red-Black tree context, to be implemented
    psi, psiF = not_psi_rb_strict, error_psiF  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "black_height": "int", "error": "bool"}
    label_filter = rb_label_filter
    pair_filter = rb_pair_filter
    return SDTAContext(psi, psiF, states, label_filter, pair_filter)
