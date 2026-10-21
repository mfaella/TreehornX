from dataclasses import dataclass
from typing import Callable, Literal

from loguru import logger
from pysmt.fnode import FNode

from treehornx.chc.sdta.psi import (
    PsiFType,
    PsiType,
    error_psiF,
    not_psi_avl,
    not_psi_bst,
    not_psi_bst_strict,
    not_psi_sll_sorted,
    not_psi_sll_sorted_strict,
    psi_avl,
    psi_bst,
    psi_bst_strict,
    psi_rb,
    psi_sll_sorted,
    psi_sll_sorted_strict,
    psiF_empty,
    root_is_black,
)
from treehornx.enum_models.core.Label import Label


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


def rb_ctx() -> SDTAContext:
    psi, psiF = psi_rb, root_is_black  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {
        "min": "int",
        "max": "int",
        "data": "int",
        "black_height": "int",
        "red": "bool",
    }
    return SDTAContext(psi, psiF, states)
