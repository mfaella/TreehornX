from dataclasses import dataclass
from typing import Callable, Literal

from treehornx.chc.psi import (
    PsiFType,
    PsiType,
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
    psi, psiF = psi_bst, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int"}
    return SDTAContext(psi, psiF, states)


def bst_strict_ctx() -> SDTAContext:
    psi, psiF = psi_bst_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int"}
    return SDTAContext(psi, psiF, states)


def sll_sorted_ctx() -> SDTAContext:
    psi, psiF = psi_sll_sorted, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int"}
    return SDTAContext(psi, psiF, states)


def sll_sorted_strict_ctx() -> SDTAContext:
    psi, psiF = psi_sll_sorted_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"data": "int"}
    return SDTAContext(psi, psiF, states)


def avl_ctx() -> SDTAContext:
    psi, psiF = psi_avl, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
    return SDTAContext(psi, psiF, states)


def avl_strict_ctx() -> SDTAContext:
    psi, psiF = psi_avl_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "height": "int"}
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
    # Placeholder for Red-Black tree context, to be implemented
    psi, psiF = psi_rb, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "black_height": "int"}
    label_filter = rb_label_filter
    pair_filter = rb_pair_filter
    return SDTAContext(psi, psiF, states, label_filter, pair_filter)

def rb_strict_ctx() -> SDTAContext:
    # Placeholder for Red-Black tree context, to be implemented
    psi, psiF = psi_rb_strict, psiF_empty  # noqa: N806
    states: dict[str, Literal["int", "bool"]] = {"min": "int", "max": "int", "data": "int", "black_height": "int"}
    label_filter = rb_label_filter
    pair_filter = rb_pair_filter
    return SDTAContext(psi, psiF, states, label_filter, pair_filter)
