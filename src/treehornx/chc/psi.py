from typing import Callable

from loguru import logger
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


def not_psi_sll_sorted(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    logger.debug(f"children_states: {children_states}, fields: {fields}, enum_fields: {enum_fields}, states: {states}")
    if children_states["next"] is None:
        return smt.And(
            smt.Equals(states["data"], fields["data"]),
            smt.Not(states["error"])
        )

    return smt.And(
        smt.Iff(states["error"], smt.Or(
            smt.LT(children_states["next"]["data"], fields["data"]),
            children_states["next"]["error"]
        )),
        smt.Equals(states["data"], fields["data"])
    )


def psi_sll_sorted_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    if children_states["next"] is None:
        return smt.Equals(states["data"], fields["data"])

    return smt.And(smt.GT(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))


def not_psi_sll_sorted_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    logger.debug(f"children_states: {children_states}, fields: {fields}, enum_fields: {enum_fields}, states: {states}")
    if children_states["next"] is None:
        logger.debug("Next state is None, returning base case for not_psi_sll_sorted_strict")
        return smt.And(
            smt.Equals(states["data"], fields["data"]),
            smt.Not(states["error"])
        )

    logger.debug("Next state is not None, proceeding with recursive case for not_psi_sll_sorted_strict")

    const = smt.And(
        smt.EqualsOrIff(states["error"], smt.Or(
            smt.LE(children_states["next"]["data"], fields["data"]),
            children_states["next"]["error"]
        )),
        smt.Equals(states["data"], fields["data"])
    )
    logger.debug(f"Constructed condition for not_psi_sll_sorted_strict: {const}")
    return const


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
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[FNode] = []

    if left_state is None and right_state is None:
        conditions.append(smt.And(
            smt.Equals(states["min"], fields["data"]),
            smt.Equals(states["max"], fields["data"]),
            smt.Equals(states["data"], fields["data"]),
            smt.Not(states["error"])
        ))
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
    conditions.append(smt.EqualsOrIff(states["error"], smt.Or(
        smt.GT(left_state["max"], fields["data"]) if left_state is not None else smt.FALSE(),
        smt.LT(right_state["min"], fields["data"]) if right_state is not None else smt.FALSE(),
        left_state["error"] if left_state is not None else smt.FALSE(),
        right_state["error"] if right_state is not None else smt.FALSE(),
    )))
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


def not_psi_bst_strict(
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
        conditions.append(smt.And(
            smt.Equals(states["min"], fields["data"]),
            smt.Equals(states["max"], fields["data"]),
            smt.Equals(states["data"], fields["data"]),
            smt.Not(states["error"])
        ))
        return smt.And(*conditions)

    if left_state is not None:
        conditions.append(smt.Equals(states["min"], left_state["min"]))
    else:
        conditions.append(smt.Equals(states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(smt.Equals(states["max"], right_state["max"]))
    else:
        conditions.append(smt.Equals(states["max"], fields["data"]))

    conditions.append(smt.Or(
        smt.GE(left_state["max"], fields["data"]) if left_state is not None else smt.FALSE(),
        smt.LE(right_state["min"], fields["data"]) if right_state is not None else smt.FALSE(),
        left_state["error"] if left_state is not None else smt.FALSE(),
        right_state["error"] if right_state is not None else smt.FALSE(),
    ))
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
        constraints.append(smt.Equals(states["height"], smt.Int(1)))

    elif left_state is None:
        assert right_state is not None
        constraints.append(smt.Equals(right_state["height"], smt.Int(1)))
        constraints.append(smt.Equals(states["height"], smt.Int(2)))

    elif right_state is None:
        assert left_state is not None
        constraints.append(smt.Equals(left_state["height"], smt.Int(1)))
        constraints.append(smt.Equals(states["height"], smt.Int(2)))

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
    states: dict[str, FNode],
) -> FNode:
    return _psi_avl_template(children_states, fields, enum_fields, states, psi_bst_strict)


def not_psi_avl(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
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


def psi_avl_wbf(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    bst = psi_bst(children_states, fields, enum_fields, states)
    left_state = children_states["left"]
    right_state = children_states["right"]

    constraints: list[FNode] = []
    constraints.append(psi_bst_strict(children_states, fields, enum_fields, states))

    if left_state is None and right_state is None:
        constraints.append(smt.Equals(states["height"], smt.Int(1)))
        constraints.append(smt.Bool(enum_fields["bf"] == "NEUTRAL"))

    elif left_state is None:
        assert right_state is not None
        constraints.append(smt.Equals(right_state["height"], smt.Int(1)))
        constraints.append(smt.Equals(states["height"], smt.Int(2)))
        constraints.append(smt.Bool(enum_fields["bf"] == "LOW_RIGHT"))

    elif right_state is None:
        assert left_state is not None
        constraints.append(smt.Equals(left_state["height"], smt.Int(1)))
        constraints.append(smt.Equals(states["height"], smt.Int(2)))
        constraints.append(smt.Bool(enum_fields["bf"] == "LOW_LEFT"))

    else:
        constraints.append(
            smt.Equals(states["height"], smt.Plus(smt.Max(left_state["height"], right_state["height"]), smt.Int(1)))
        )
        diff = smt.Minus(left_state["height"], right_state["height"])
        constraints.append(smt.And(smt.GE(diff, smt.Int(-1)), smt.LE(diff, smt.Int(1))))
        constraints.append(smt.Implies(smt.Equals(diff, smt.Int(-1)), smt.Bool(enum_fields["bf"] == "LOW_LEFT")))
        constraints.append(smt.Implies(smt.Equals(diff, smt.Int(0)), smt.Bool(enum_fields["bf"] == "NEUTRAL")))
        constraints.append(smt.Implies(smt.Equals(diff, smt.Int(1)), smt.Bool(enum_fields["bf"] == "LOW_RIGHT")))

    return smt.And(bst, *constraints)


def not_psi_avl_wbf(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    # raise NotImplementedError("not_psi_avl_wbf is not implemented yet")
    conditions: list[FNode] = []
    error_conditions: list[FNode] = []

    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions.append(smt.Equals(states["data"], fields["data"]))

    if left_state is None and right_state is None:
        error_conditions.append(smt.Not(smt.Equals(states["height"], smt.Int(1))))
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))
        # conditions.append(smt.Bool(enum_fields["bf"] != "NEUTRAL")) this conditions is added in the pair filter

    elif left_state is None and right_state is not None:

        conditions.append(smt.Equals(states["min"], states["data"]))
        conditions.append(smt.Equals(states["max"], right_state["max"]))
        error_conditions.append(smt.LE(right_state["min"], states["data"]))
        error_conditions.append(smt.NotEquals(right_state["height"], smt.Int(1)))
        error_conditions.append(smt.NotEquals(states["height"], smt.Int(2)))
        error_conditions.append(smt.Bool(enum_fields["bf"] != "LOW_RIGHT"))

    elif right_state is None and left_state is not None:
        conditions.append(smt.Equals(states["max"], states["data"]))
        conditions.append(smt.Equals(states["min"], left_state["min"]))
        error_conditions.append(smt.GE(left_state["max"], states["data"]))
        error_conditions.append(smt.NotEquals(left_state["height"], smt.Int(1)))
        error_conditions.append(smt.NotEquals(states["height"], smt.Int(2)))
        error_conditions.append(smt.Bool(enum_fields["bf"] != "LOW_LEFT"))

    else:

        assert left_state is not None and right_state is not None

        conditions.append(smt.Equals(states["min"], left_state["min"]))
        conditions.append(smt.Equals(states["max"], right_state["max"]))

        left_height = left_state["height"]
        right_height = right_state["height"]
        diff = smt.Minus(left_height, right_height)
        error_conditions.append(smt.Or(smt.LT(diff, smt.Int(-1)), smt.GT(diff, smt.Int(1))))
        error_conditions.append(smt.Implies(smt.Equals(diff, smt.Int(-1)), smt.Bool(enum_fields["bf"] != "LOW_LEFT")))
        error_conditions.append(smt.Implies(smt.Equals(diff, smt.Int(0)), smt.Bool(enum_fields["bf"] != "NEUTRAL")))
        error_conditions.append(smt.Implies(smt.Equals(diff, smt.Int(1)), smt.Bool(enum_fields["bf"] != "LOW_RIGHT")))

    error = smt.Iff(states["error"], smt.Or(*error_conditions))
    conditions.append(error)

    return smt.And(*conditions)


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


def not_psi_rb(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    conditions: list[FNode] = []
    error_conditions: list[FNode] = []

    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions.append(smt.Equals(states["data"], fields["data"]))

    if left_state is None and right_state is None:
        if enum_fields["color"] == "RED":
            conditions.append(smt.Equals(states["black_height"], smt.Int(0)))
        else: # enum_fields["color"] == "BLACK"
            conditions.append(smt.Equals(states["black_height"], smt.Int(1)))
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))

    else:

        if left_state is not None:
            if enum_fields["color"] == "RED":
                conditions.append(smt.Equals(left_state["black_height"], states["black_height"]))
                error_conditions.append(smt.GT(left_state["min"], states["data"]))
            else: # BLACK
                conditions.append(smt.Equals(smt.Plus(left_state["black_height"], smt.Int(1)), states["black_height"]))
            conditions.append(smt.Equals(states["min"], left_state["min"]))
            error_conditions.append(left_state["error"])
        else:
            conditions.append(smt.Equals(states["min"], states["data"]))

        if right_state is not None:
            if enum_fields["color"] == "RED":
                conditions.append(smt.Equals(right_state["black_height"], states["black_height"]))
                error_conditions.append(smt.LT(right_state["max"], states["data"]))
            else: # BLACK
                conditions.append(smt.Equals(smt.Plus(right_state["black_height"], smt.Int(1)), states["black_height"]))
            conditions.append(smt.Equals(states["min"], right_state["min"]))
            error_conditions.append(right_state["error"])
        else:
            conditions.append(smt.Equals(states["min"], states["data"]))

        left_height  = left_state["black_height"] if left_state is not None else smt.Int(0)
        right_height = right_state["black_height"] if right_state is not None else smt.Int(0)
        error_conditions.append(smt.Equals(left_height, right_height))

    error = smt.Iff(states["error"], smt.Or(*error_conditions))
    conditions.append(error)
    return smt.And(*conditions)


def psi_rb_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    return _psi_rb_template(children_states, fields, enum_fields, states, psi_bst_strict)


def not_psi_rb_strict(
    children_states: dict[str, dict[str, FNode] | None],
    fields: dict[str, FNode],
    enum_fields: dict[str, str],
    states: dict[str, FNode]
) -> FNode:
    conditions: list[FNode] = []
    error_conditions: list[FNode] = []

    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions.append(smt.Equals(states["data"], fields["data"]))

    if left_state is None and right_state is None:
        if enum_fields["color"] == "RED":
            conditions.append(smt.Equals(states["black_height"], smt.Int(0)))
        else: # enum_fields["color"] == "BLACK"
            conditions.append(smt.Equals(states["black_height"], smt.Int(1)))
        conditions.append(smt.Equals(states["min"], fields["data"]))
        conditions.append(smt.Equals(states["max"], fields["data"]))

    else:

        if left_state is not None:
            if enum_fields["color"] == "RED":
                conditions.append(smt.Equals(left_state["black_height"], states["black_height"]))
                error_conditions.append(smt.GT(left_state["min"], states["data"]))
            else: # BLACK
                conditions.append(smt.Equals(smt.Plus(left_state["black_height"], smt.Int(1)), states["black_height"]))
            conditions.append(smt.Equals(states["min"], left_state["min"]))
            error_conditions.append(left_state["error"])
        else:
            conditions.append(smt.Equals(states["min"], states["data"]))

        if right_state is not None:
            if enum_fields["color"] == "RED":
                conditions.append(smt.Equals(right_state["black_height"], states["black_height"]))
                error_conditions.append(smt.LT(right_state["max"], states["data"]))
            else: # BLACK
                conditions.append(smt.Equals(smt.Plus(right_state["black_height"], smt.Int(1)), states["black_height"]))
            conditions.append(smt.Equals(states["min"], right_state["min"]))
            error_conditions.append(right_state["error"])
        else:
            conditions.append(smt.Equals(states["min"], states["data"]))

        left_height  = left_state["black_height"] if left_state is not None else smt.Int(0)
        right_height = right_state["black_height"] if right_state is not None else smt.Int(0)
        error_conditions.append(smt.Equals(left_height, right_height))

    error = smt.Iff(states["error"], smt.Or(*error_conditions))
    conditions.append(error)
    return smt.And(*conditions)


def psiF_empty(states: dict[str, FNode]) -> FNode:  # noqa: N802
    return smt.TRUE()


def error_psiF(states: dict[str, FNode]) -> FNode:
    return states["error"]


    # return smt.And(smt.GE(children_states["next"]["data"], fields["data"]), smt.Equals(states["data"], fields["data"]))
