from typing import Callable, TypeAlias

import pysmt.shortcuts as smt
from loguru import logger
from pysmt.fnode import FNode


PsiType: TypeAlias = Callable[
    [
        dict[str, dict[str, FNode] | None],  # children states
        dict[str, FNode],  # fields
        dict[str, FNode],
    ],  # states
    FNode,
]
PsiFType: TypeAlias = Callable[[dict[str, FNode]], FNode]


def psi_sll_sorted(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GE(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def not_psi_sll_sorted(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.And(smt.Equals(states["data"], fields["data"]), smt.Not(states["error"]))

    return smt.And(
        smt.Iff(
            states["error"],
            smt.Or(smt.LT(children_states["next"]["data"], fields["data"]), children_states["next"]["error"]),
        ),
        smt.Equals(states["data"], fields["data"]),
    )


def psi_sll_sorted_strict(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GT(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def not_psi_sll_sorted_strict(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        logger.debug("Next state is None, returning base case for not_psi_sll_sorted_strict")
        return smt.And(smt.Equals(states["data"], fields["data"]), smt.Not(states["error"]))

    logger.debug("Next state is not None, proceeding with recursive case for not_psi_sll_sorted_strict")

    const = smt.And(
        smt.EqualsOrIff(
            states["error"],
            smt.Or(smt.LE(children_states["next"]["data"], fields["data"]), children_states["next"]["error"]),
        ),
        smt.Equals(states["data"], fields["data"]),
    )
    logger.debug(f"Constructed condition for not_psi_sll_sorted_strict: {const}")
    return const


def psi_bst(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[FNode] = []

    if left_state is None and right_state is None:
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))
        return smt.And(*conditions)

    if left_state is not None:
        conditions.append(smt.LE(left_state["max"], fields["data"]))
        conditions.append(smt.Equals(states["min"], left_state["min"]))
    else:
        conditions.append(smt.Equals(states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(smt.GE(right_state["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], right_state["max"]))
    else:
        conditions.append(smt.Equals(states["max"], fields["data"]))

    conditions.append(smt.Equals(states["data"], fields["data"]))
    return smt.And(*conditions)


def not_psi_bst(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[FNode] = []

    if left_state is None and right_state is None:
        conditions.append(
            smt.And(
                smt.Equals(states["min"], fields["data"]),
                smt.Equals(states["max"], fields["data"]),
                smt.Equals(states["data"], fields["data"]),
                smt.Not(states["error"]),
            )
        )
        return smt.And(*conditions)

    if left_state is not None:
        conditions.append(smt.Equals(states["min"], left_state["min"]))
    else:
        conditions.append(smt.Equals(states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(smt.Equals(states["max"], right_state["max"]))
    else:
        conditions.append(smt.Equals(states["max"], fields["data"]))

    conditions.append(smt.Equals(states["data"], fields["data"]))
    conditions.append(
        smt.EqualsOrIff(
            states["error"],
            smt.Or(
                smt.GT(left_state["max"], fields["data"]) if left_state is not None else smt.FALSE(),
                smt.LT(right_state["min"], fields["data"]) if right_state is not None else smt.FALSE(),
                left_state["error"] if left_state is not None else smt.FALSE(),
                right_state["error"] if right_state is not None else smt.FALSE(),
            ),
        )
    )
    return smt.And(*conditions)


def psi_bst_strict(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
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


def not_psi_bst_strict(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[FNode] = []
    conditions.append(smt.Equals(states["data"], fields["data"]))

    if left_state is None and right_state is None:
        conditions.append(
            smt.And(
                smt.Equals(states["min"], fields["data"]),
                smt.Equals(states["max"], fields["data"]),
                smt.Equals(states["data"], fields["data"]),
                smt.Not(states["error"]),
            )
        )
        return smt.And(*conditions)

    if left_state is not None:
        conditions.append(smt.Equals(states["min"], left_state["min"]))
    else:
        conditions.append(smt.Equals(states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(smt.Equals(states["max"], right_state["max"]))
    else:
        conditions.append(smt.Equals(states["max"], fields["data"]))

    conditions.append(
        smt.Or(
            smt.GE(left_state["max"], fields["data"]) if left_state is not None else smt.FALSE(),
            smt.LE(right_state["min"], fields["data"]) if right_state is not None else smt.FALSE(),
            left_state["error"] if left_state is not None else smt.FALSE(),
            right_state["error"] if right_state is not None else smt.FALSE(),
        )
    )
    return smt.And(*conditions)


def _psi_avl_template(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    states: dict[str, FNode],
    bst_psi: PsiType,
) -> FNode:
    bst = bst_psi(children_states, fields, states)
    left_state = children_states["left"]
    right_state = children_states["right"]

    constraints: list[FNode] = []

    if left_state is None and right_state is None:
        constraints.append(smt.Equals(states["height"], smt.Int(1)))
        constraints.append(smt.Equals(fields["bal"], smt.Int(0)))

    elif left_state is None:
        assert right_state is not None
        constraints.append(smt.Equals(right_state["height"], smt.Int(1)))
        constraints.append(smt.Equals(states["height"], smt.Int(2)))
        constraints.append(smt.Equals(fields["bal"], smt.Int(1)))

    elif right_state is None:
        assert left_state is not None
        constraints.append(smt.Equals(left_state["height"], smt.Int(1)))
        constraints.append(smt.Equals(states["height"], smt.Int(2)))
        constraints.append(smt.Equals(fields["bal"], smt.Int(-1)))

    else:
        constraints.append(
            smt.Equals(states["height"], smt.Plus(smt.Max(left_state["height"], right_state["height"]), smt.Int(1)))
        )
        diff = smt.Minus(right_state["height"], left_state["height"])
        constraints.append(smt.Equals(fields["bal"], diff))

    return smt.And(bst, *constraints)


def psi_avl(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    states: dict[str, FNode],
) -> FNode:
    return _psi_avl_template(children_states, fields, states, psi_bst_strict)


def not_psi_avl(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    states: dict[str, FNode],
) -> FNode:
    conditions: list[FNode] = []
    error_conditions: list[FNode] = []

    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions.append(smt.Equals(states["height"], fields["height"]))
    conditions.append(smt.Equals(states["data"], fields["data"]))

    if left_state is None and right_state is None:
        error_conditions.append(smt.NotEquals(states["height"], smt.Int(1)))
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))

    elif left_state is None or right_state is None:
        if left_state is None:
            assert right_state is not None
            error_conditions.append(smt.NotEquals(right_state["height"], smt.Int(1)))
            error_conditions.append(smt.NotEquals(states["height"], smt.Int(2)))
            error_conditions.append(smt.LE(right_state["min"], states["data"]))
            conditions.append(smt.Equals(states["min"], states["data"]))
            conditions.append(smt.Equals(states["max"], right_state["max"]))

        if right_state is None:
            assert left_state is not None
            error_conditions.append(smt.NotEquals(left_state["height"], smt.Int(1)))
            error_conditions.append(smt.NotEquals(states["height"], smt.Int(2)))
            error_conditions.append(smt.GE(left_state["max"], states["data"]))
            conditions.append(smt.Equals(states["max"], states["data"]))
            conditions.append(smt.Equals(states["min"], left_state["min"]))

    else:
        max_height = smt.Max(left_state["height"], right_state["height"])
        error_conditions.append(smt.NotEquals(smt.Plus(max_height, smt.Int(1)), states["height"]))
        diff_height = smt.Minus(left_state["height"], right_state["height"])
        error_conditions.append(smt.GT(diff_height, smt.Int(1)))
        error_conditions.append(smt.LT(diff_height, smt.Int(-1)))
        error_conditions.append(smt.GE(left_state["max"], states["data"]))
        error_conditions.append(smt.LE(right_state["min"], states["data"]))
        error_conditions.append(left_state["error"])
        error_conditions.append(right_state["error"])
        conditions.append(smt.Equals(states["min"], left_state["min"]))
        conditions.append(smt.Equals(states["max"], right_state["max"]))

    error = smt.Iff(states["error"], smt.Or(*error_conditions))
    conditions.append(error)

    return smt.And(*conditions)


def _psi_rb_template(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    states: dict[str, FNode],
    bst_psi: PsiType,
) -> FNode:
    """black_height counts the black nodes on every path down to nil, a nil child is black with black height 0.
    The colour of the node is its data field `red`."""
    red, black_height = states["red"], states["black_height"]
    children = [state for state in (children_states["left"], children_states["right"]) if state is not None]
    children_height = [state["black_height"] for state in children] + [smt.Int(0)] * (2 - len(children))

    return smt.And(
        smt.Iff(red, fields["red"]),
        smt.Equals(children_height[0], children_height[1]),
        smt.Equals(black_height, smt.Plus(children_height[0], smt.Ite(red, smt.Int(0), smt.Int(1)))),
        *(smt.Implies(red, smt.Not(state["red"])) for state in children),
        bst_psi(children_states, fields, states),
    )


def psi_rb(
    children_states: dict[str, dict[str, FNode] | None], fields: dict[str, FNode], states: dict[str, FNode]
) -> FNode:
    return _psi_rb_template(children_states, fields, states, psi_bst_strict)


# def not_psi_rb(
#     children_states: dict[str, dict[str, FNode] | None],
#     fields: dict[str, FNode],
#     enum_fields: dict[str, str],
#     states: dict[str, FNode]
# ) -> FNode:
#     conditions: list[FNode] = []
#     error_conditions: list[FNode] = []

#     left_state = children_states["left"]
#     right_state = children_states["right"]

#     conditions.append(smt.Equals(states["data"], fields["data"]))

#     if left_state is None and right_state is None:
#         if enum_fields["color"] == "RED":
#             conditions.append(smt.Equals(states["black_height"], smt.Int(0)))
#         else: # enum_fields["color"] == "BLACK"
#             conditions.append(smt.Equals(states["black_height"], smt.Int(1)))
#         conditions.append(smt.Equals(states["min"], fields["data"]))
#         conditions.append(smt.Equals(states["max"], fields["data"]))

#     else:

#         if left_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(smt.Equals(left_state["black_height"], states["black_height"]))
#                 error_conditions.append(smt.GT(left_state["min"], states["data"]))
#             else: # BLACK
#                 conditions.append(smt.Equals(smt.Plus(left_state["black_height"], smt.Int(1)), states["black_height"]))
#             conditions.append(smt.Equals(states["min"], left_state["min"]))
#             error_conditions.append(left_state["error"])
#         else:
#             conditions.append(smt.Equals(states["min"], states["data"]))

#         if right_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(smt.Equals(right_state["black_height"], states["black_height"]))
#                 error_conditions.append(smt.LT(right_state["max"], states["data"]))
#             else: # BLACK
#                 conditions.append(smt.Equals(smt.Plus(right_state["black_height"], smt.Int(1)), states["black_height"]))
#             conditions.append(smt.Equals(states["min"], right_state["min"]))
#             error_conditions.append(right_state["error"])
#         else:
#             conditions.append(smt.Equals(states["min"], states["data"]))

#         left_height  = left_state["black_height"] if left_state is not None else smt.Int(0)
#         right_height = right_state["black_height"] if right_state is not None else smt.Int(0)
#         error_conditions.append(smt.Equals(left_height, right_height))

#     error = smt.Iff(states["error"], smt.Or(*error_conditions))
#     conditions.append(error)
#     return smt.And(*conditions)


# def psi_rb_strict(
#     children_states: dict[str, dict[str, FNode] | None],
#     fields: dict[str, FNode],
#     enum_fields: dict[str, str],
#     states: dict[str, FNode]
# ) -> FNode:
#     return _psi_rb_template(children_states, fields, enum_fields, states, psi_bst_strict)


# def not_psi_rb_strict(
#     children_states: dict[str, dict[str, FNode] | None],
#     fields: dict[str, FNode],
#     enum_fields: dict[str, str],
#     states: dict[str, FNode]
# ) -> FNode:
#     conditions: list[FNode] = []
#     error_conditions: list[FNode] = []

#     left_state = children_states["left"]
#     right_state = children_states["right"]

#     conditions.append(smt.Equals(states["data"], fields["data"]))

#     if left_state is None and right_state is None:
#         if enum_fields["color"] == "RED":
#             conditions.append(smt.Equals(states["black_height"], smt.Int(0)))
#         else: # enum_fields["color"] == "BLACK"
#             conditions.append(smt.Equals(states["black_height"], smt.Int(1)))
#         conditions.append(smt.Equals(states["min"], fields["data"]))
#         conditions.append(smt.Equals(states["max"], fields["data"]))

#     else:

#         if left_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(smt.Equals(left_state["black_height"], states["black_height"]))
#                 error_conditions.append(smt.GT(left_state["min"], states["data"]))
#             else: # BLACK
#                 conditions.append(smt.Equals(smt.Plus(left_state["black_height"], smt.Int(1)), states["black_height"]))
#             conditions.append(smt.Equals(states["min"], left_state["min"]))
#             error_conditions.append(left_state["error"])
#         else:
#             conditions.append(smt.Equals(states["min"], states["data"]))

#         if right_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(smt.Equals(right_state["black_height"], states["black_height"]))
#                 error_conditions.append(smt.LT(right_state["max"], states["data"]))
#             else: # BLACK
#                 conditions.append(smt.Equals(smt.Plus(right_state["black_height"], smt.Int(1)), states["black_height"]))
#             conditions.append(smt.Equals(states["min"], right_state["min"]))
#             error_conditions.append(right_state["error"])
#         else:
#             conditions.append(smt.Equals(states["min"], states["data"]))

#         left_height  = left_state["black_height"] if left_state is not None else smt.Int(0)
#         right_height = right_state["black_height"] if right_state is not None else smt.Int(0)
#         error_conditions.append(smt.Equals(left_height, right_height))

#     error = smt.Iff(states["error"], smt.Or(*error_conditions))
#     conditions.append(error)
#     return smt.And(*conditions)


def psiF_empty(states: dict[str, FNode]) -> FNode:  # noqa: N802
    return smt.TRUE()


def error_psiF(states: dict[str, FNode]) -> FNode:  # noqa: N802
    return states["error"]

    # return smt.And(smt.GE(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def root_is_black(states: dict[str, FNode]) -> FNode:
    return smt.Not(states["red"])
