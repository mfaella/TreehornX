
from dataclasses import dataclass
from typing import Literal
from treehornx.chc.pre.psi import PsiFType, PsiType, psi_avl, psi_avl_strict, psi_bst, psi_bst_strict, psi_sll_sorted, psi_sll_sorted_strict, psiF_empty


@dataclass(slots=True, frozen=True)
class PreContext:
    psi: PsiType
    psiF: PsiFType
    states: dict[str, Literal["int", "bool"]]

def bst_ctx() -> PreContext:
    psi, psiF = psi_bst, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int"}
    return PreContext(psi, psiF, states)

def bst_strict_ctx() -> PreContext:
    psi, psiF = psi_bst_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int"}
    return PreContext(psi, psiF, states)

def sll_sorted_ctx() -> PreContext:
    psi, psiF = psi_sll_sorted, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int"}
    return PreContext(psi, psiF, states)

def sll_sorted_strict_ctx() -> PreContext:
    psi, psiF = psi_sll_sorted_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int"}
    return PreContext(psi, psiF, states)

def avl_ctx() -> PreContext:
    psi, psiF = psi_avl, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
    return PreContext(psi, psiF, states)

def avl_strict_ctx() -> PreContext:
    psi, psiF = psi_avl_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
    return PreContext(psi, psiF, states)
