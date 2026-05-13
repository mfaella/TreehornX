from typing import Callable

import pysmt.shortcuts as smt
from pysmt.fnode import FNode


type PsiType = Callable[
    [dict[str, dict[str, FNode] | None], # children states
    dict[str, FNode], # fields
    dict[str, str], # enum fields
    dict[str, FNode]], # states
FNode]
type PsiFType = Callable[[dict[str, FNode]], FNode]


def psi_sll_sorted(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GE(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def psi_sll_sorted_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GT(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def psi_bst(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
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
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
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
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode],
    bst_psi: PsiType,
) -> FNode:
    bst = bst_psi(children_states, fields, enum_fields, states)
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
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    return _psi_avl_template(children_states, fields, enum_fields, states, psi_bst)


def psi_avl_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode],
) -> FNode:
    return _psi_avl_template(children_states, fields, enum_fields, states, psi_bst_strict)


def _psi_rb_template(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode],
    bst_psi: PsiType
) -> FNode:

    assert enum_fields["color"] in {"RED", "BLACK"}, f"Invalid color: {enum_fields['color']}"

    left_state = children_states["left"]
    right_state = children_states["right"]

    constraints: list[FNode] = []
    height_constraint: FNode = smt.TRUE()

    if left_state is None and right_state is None:
        if enum_fields["color"] == "RED":
            height_constraint = smt.Equals(states["black_height"], smt.Int(0))
        elif enum_fields["color"] == "BLACK":
            height_constraint = smt.Equals(states["black_height"], smt.Int(1))

    elif right_state is None:
        assert left_state is not None
        if enum_fields["color"] == "RED":
            # height_constraint = smt.Equals(states["black_height"], left_state["black_height"])
            height_constraint = smt.FALSE()
        elif enum_fields["color"] == "BLACK":
            # height_constraint = smt.Equals(
            #     states["black_height"],
            #     smt.Plus(
            #         left_state["black_height"],
            #         smt.Int(1)
            #     )
            # )
            height_constraint = smt.And(
                smt.Equals(states["black_height"], smt.Plus(left_state["black_height"], smt.Int(1))),
                smt.Equals(left_state["black_height"], smt.Int(0))
            )

    elif left_state is None:
        if enum_fields["color"] == "RED":
            # height_constraint = smt.Equals(states["black_height"], right_state["black_height"])
            height_constraint = smt.FALSE()
        elif enum_fields["color"] == "BLACK":
            # height_constraint = smt.Equals(
            #     states["black_height"],
            #     smt.Plus(
            #         right_state["black_height"],
            #         smt.Int(1)
            #     )
            # )
            height_constraint = smt.And(
                smt.Equals(states["black_height"], smt.Plus(right_state["black_height"], smt.Int(1))),
                smt.Equals(right_state["black_height"], smt.Int(0))
            )

    else:
        assert left_state is not None and right_state is not None
        children_height_constraint = smt.Equals(left_state["black_height"], right_state["black_height"])
        if enum_fields["color"] == "RED":
            height_constraint = smt.And(
                children_height_constraint,
                smt.Equals(states["black_height"], left_state["black_height"])
            )
        elif enum_fields["color"] == "BLACK":
            height_constraint = smt.And(
                children_height_constraint,
                smt.Equals(
                    states["black_height"],
                    smt.Plus(
                        left_state["black_height"],
                        smt.Int(1)
                    )
                )
            )

    assert height_constraint != smt.TRUE()

    constraints.append(height_constraint)
    constraints.append(bst_psi(children_states, fields, enum_fields, states))

    return smt.And(*constraints)

def psi_rb(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    return _psi_rb_template(children_states, fields, enum_fields, states, psi_bst)

def psi_rb_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    return _psi_rb_template(children_states, fields, enum_fields, states, psi_bst_strict)


def psiF_empty(states: dict[str, FNode]) -> FNode:  # noqa: N802
    return smt.TRUE()
