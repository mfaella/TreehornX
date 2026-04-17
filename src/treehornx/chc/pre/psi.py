from dataclasses import dataclass
from typing import Callable, override

import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx.enum_labels.core.Label import Label

type PsiType = Callable[[dict[str | int, dict[str, FNode] | None], dict[str, FNode], dict[str, FNode]], FNode]
type PsiFType = Callable[[dict[str, FNode]], FNode]

def psi_sll_sorted(
    children_states: dict[str | int, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GE(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def psi_sll_sorted_strict(
    children_states: dict[str | int, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GT(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def psi_bst(
    children_states: dict[str | int, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[FNode] = []

    if left_state is None and right_state is None:
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))
        return smt.TRUE()

    if left_state is not None:
        conditions.append(smt.LE(left_state["max"], fields["data"]))
        conditions.append(smt.Equals(states["data"], fields["data"]))
        conditions.append(smt.Equals(states["min"], left_state["min"]))
    else:
        conditions.append(smt.Equals(states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(smt.GE(right_state["min"], fields["data"]))
        conditions.append(smt.Equals(states["data"], fields["data"]))
        conditions.append(smt.Equals(states["max"], right_state["max"]))
    else:
        conditions.append(smt.Equals(states["max"], fields["data"]))

    return smt.And(*conditions)


def psi_bst_strict(
    children_states: dict[str | int, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[FNode] = []
    conditions.append(smt.Equals(states["data"], fields["data"]))

    if left_state is None and right_state is None:
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))
        return smt.And(*conditions)

    if left_state is not None:
        conditions.append(smt.LT(left_state["max"], fields["data"]))
        conditions.append(smt.Equals(states["min"], left_state["min"]))
    else:
        conditions.append(smt.Equals(states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(smt.GT(right_state["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], right_state["max"]))
    else:
        conditions.append(smt.Equals(states["max"], fields["data"]))

    return smt.And(*conditions)


def _psi_avl_template(
    children_states: dict[str | int, dict[str, FNode] | None],
    fields: dict[str, FNode],
    states: dict[str, FNode],
    bst_psi: PsiType,
) -> FNode:
    bst = bst_psi(children_states, fields, states)
    left_state = children_states["left"]
    right_state = children_states["right"]

    constraints: list[FNode] = []

    if left_state is None and right_state is None:
        constraints.append(smt.Equals(states["height"], smt.Int(0)))

    elif left_state is None:
        assert right_state is not None
        constraints.append(smt.Equals(right_state["height"], smt.Int(0)))
        constraints.append(smt.Equals(states["height"], smt.Int(1)))

    elif right_state is None:
        assert left_state is not None
        constraints.append(smt.Equals(left_state["height"], smt.Int(0)))
        constraints.append(smt.Equals(states["height"], smt.Int(1)))

    else:
        constraints.append(
            smt.Equals(states["height"], smt.Plus(smt.Max(left_state["height"], right_state["height"]), smt.Int(1)))
        )
        diff = smt.Minus(left_state["height"], right_state["height"])
        constraints.append(smt.And(smt.GE(diff, smt.Int(-1)), smt.LE(diff, smt.Int(1))))

    constraints.append(smt.Equals(states["height"], fields["height"]))

    return smt.And(bst, *constraints)


def psi_avl(
    children_states: dict[str | int, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    return _psi_avl_template(children_states, fields, states, psi_bst)


def psi_avl_strict(
    children_states: dict[str | int, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    return _psi_avl_template(children_states, fields, states, psi_bst_strict)


def psiF_empty(states: dict[str, FNode]) -> FNode:  # noqa: N802
    # This is a placeholder implementation. The actual implementation would depend on the specific properties of the label and states.
    # For example, if the label represents a sorted singly linked list, we might want to check that the elements are in sorted order.
    # This is just a dummy implementation and should be replaced with the actual logic.
    return smt.TRUE()
