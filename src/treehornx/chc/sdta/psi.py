from typing import Callable, Mapping, TypeAlias

from loguru import logger

from treehornx.chc.smt import sexpr as sx


PsiType: TypeAlias = Callable[
    [
        Mapping[str, Mapping[str, sx.SExpr] | None],  # children states
        Mapping[str, sx.SExpr],  # fields
        Mapping[str, sx.SExpr],
    ],  # states
    sx.SExpr,
]
PsiFType: TypeAlias = Callable[[Mapping[str, sx.SExpr]], sx.SExpr]


def psi_sll_sorted(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    if children_states["next"] is None:
        return sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"])

    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.GE, children_states["next"]["data"], fields["data"]),
        sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
    )


def not_psi_sll_sorted(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    if children_states["next"] is None:
        return sx.OpExpr(
            sx.Operator.AND,
            sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
            sx.OpExpr(sx.Operator.NOT, states["error"]),
        )

    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(
            sx.Operator.EQ,
            states["error"],
            sx.OpExpr(
                sx.Operator.OR,
                sx.OpExpr(sx.Operator.LT, children_states["next"]["data"], fields["data"]),
                children_states["next"]["error"],
            ),
        ),
        sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
    )


def psi_sll_sorted_strict(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    if children_states["next"] is None:
        return sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"])

    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.GT, children_states["next"]["data"], fields["data"]),
        sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
    )


def not_psi_sll_sorted_strict(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    if children_states["next"] is None:
        logger.debug("Next state is None, returning base case for not_psi_sll_sorted_strict")
        return sx.OpExpr(
            sx.Operator.AND,
            sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
            sx.OpExpr(sx.Operator.NOT, states["error"]),
        )

    logger.debug("Next state is not None, proceeding with recursive case for not_psi_sll_sorted_strict")

    const = sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(
            sx.Operator.EQ,
            states["error"],
            sx.OpExpr(
                sx.Operator.OR,
                sx.OpExpr(sx.Operator.LE, children_states["next"]["data"], fields["data"]),
                children_states["next"]["error"],
            ),
        ),
        sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
    )
    logger.debug(f"Constructed condition for not_psi_sll_sorted_strict: {const}")
    return const


def psi_bst(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[sx.SExpr] = []

    if left_state is None and right_state is None:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))
        return sx.OpExpr(sx.Operator.AND, *conditions)

    if left_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.LE, left_state["max"], fields["data"]))
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.GE, right_state["min"], fields["data"]))
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], right_state["max"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))

    conditions.append(sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]))
    return sx.OpExpr(sx.Operator.AND, *conditions)


def not_psi_bst(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[sx.SExpr] = []

    if left_state is None and right_state is None:
        return sx.OpExpr(
            sx.Operator.AND,
            sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]),
            sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]),
            sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
            sx.OpExpr(sx.Operator.NOT, states["error"]),
        )

    if left_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], right_state["max"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))

    conditions.append(sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]))
    conditions.append(
        sx.OpExpr(
            sx.Operator.EQ,
            states["error"],
            sx.OpExpr(
                sx.Operator.OR,
                sx.OpExpr(sx.Operator.GT, left_state["max"], fields["data"]) if left_state is not None else sx.FALSE,
                sx.OpExpr(sx.Operator.LT, right_state["min"], fields["data"]) if right_state is not None else sx.FALSE,
                left_state["error"] if left_state is not None else sx.FALSE,
                right_state["error"] if right_state is not None else sx.FALSE,
            ),
        )
    )
    return sx.OpExpr(sx.Operator.AND, *conditions)


def psi_bst_strict(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[sx.SExpr] = []
    conditions.append(sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]))

    if left_state is None and right_state is None:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))
        return sx.OpExpr(sx.Operator.AND, *conditions)

    if left_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.LT, left_state["max"], fields["data"]))
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.GT, right_state["min"], fields["data"]))
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], right_state["max"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))

    return sx.OpExpr(sx.Operator.AND, *conditions)


def not_psi_bst_strict(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    left_state = children_states["left"]
    right_state = children_states["right"]

    conditions: list[sx.SExpr] = []
    conditions.append(sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]))

    if left_state is None and right_state is None:
        conditions.append(
            sx.OpExpr(
                sx.Operator.AND,
                sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]),
                sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]),
                sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
                sx.OpExpr(sx.Operator.NOT, states["error"]),
            )
        )
        return sx.OpExpr(sx.Operator.AND, *conditions)

    if left_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))

    if right_state is not None:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], right_state["max"]))
    else:
        conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))

    conditions.append(
        sx.OpExpr(
            sx.Operator.OR,
            sx.OpExpr(sx.Operator.GE, left_state["max"], fields["data"]) if left_state is not None else sx.FALSE,
            sx.OpExpr(sx.Operator.LE, right_state["min"], fields["data"]) if right_state is not None else sx.FALSE,
            left_state["error"] if left_state is not None else sx.FALSE,
            right_state["error"] if right_state is not None else sx.FALSE,
        )
    )
    return sx.OpExpr(sx.Operator.AND, *conditions)


def _psi_avl_template(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
    bst_psi: PsiType,
) -> sx.SExpr:
    bst = bst_psi(children_states, fields, states)
    left_state = children_states["left"]
    right_state = children_states["right"]

    constraints: list[sx.SExpr] = []

    if left_state is None and right_state is None:
        constraints.append(sx.OpExpr(sx.Operator.EQ, states["height"], sx.Constant(1)))
        constraints.append(sx.OpExpr(sx.Operator.EQ, fields["bal"], sx.Constant(0)))

    elif left_state is None:
        assert right_state is not None
        constraints.append(sx.OpExpr(sx.Operator.EQ, right_state["height"], sx.Constant(1)))
        constraints.append(sx.OpExpr(sx.Operator.EQ, states["height"], sx.Constant(2)))
        constraints.append(sx.OpExpr(sx.Operator.EQ, fields["bal"], sx.Constant(1)))

    elif right_state is None:
        assert left_state is not None
        constraints.append(sx.OpExpr(sx.Operator.EQ, left_state["height"], sx.Constant(1)))
        constraints.append(sx.OpExpr(sx.Operator.EQ, states["height"], sx.Constant(2)))
        constraints.append(sx.OpExpr(sx.Operator.EQ, fields["bal"], sx.Constant(-1)))

    else:
        constraints.append(
            sx.OpExpr(
                sx.Operator.EQ,
                states["height"],
                sx.OpExpr(sx.Operator.ADD, sx.Max(left_state["height"], right_state["height"]), sx.Constant(1)),
            )
        )
        diff = sx.OpExpr(sx.Operator.SUB, right_state["height"], left_state["height"])
        constraints.append(sx.OpExpr(sx.Operator.EQ, fields["bal"], diff))
        # the balance of an AVL node is in {-1, 0, 1}
        constraints.append(sx.OpExpr(sx.Operator.LE, fields["bal"], sx.Constant(1)))
        constraints.append(sx.OpExpr(sx.Operator.GE, fields["bal"], sx.Constant(-1)))

    return sx.OpExpr(sx.Operator.AND, bst, *constraints)


def psi_avl(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    return _psi_avl_template(children_states, fields, states, psi_bst_strict)


def not_psi_avl(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The negation of `psi_avl`: `error` holds iff the subtree is not a strict bst whose `bal` field is
    height(right) - height(left) in {-1, 0, 1} at every node. The other states are computed for every subtree, so
    the relation is total."""
    left_state = children_states["left"]
    right_state = children_states["right"]
    data = fields["data"]

    left_height = left_state["height"] if left_state is not None else sx.Constant(0)
    right_height = right_state["height"] if right_state is not None else sx.Constant(0)
    diff = sx.OpExpr(sx.Operator.SUB, right_height, left_height)

    conditions: list[sx.SExpr] = [
        sx.OpExpr(sx.Operator.EQ, states["data"], data),
        sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"] if left_state is not None else data),
        sx.OpExpr(sx.Operator.EQ, states["max"], right_state["max"] if right_state is not None else data),
        sx.OpExpr(sx.Operator.EQ, states["height"], sx.OpExpr(sx.Operator.ADD, sx.Max(left_height, right_height), 1)),
    ]
    error_conditions: list[sx.SExpr] = [
        sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, fields["bal"], diff)),
        sx.OpExpr(sx.Operator.GT, fields["bal"], sx.Constant(1)),
        sx.OpExpr(sx.Operator.LT, fields["bal"], sx.Constant(-1)),
    ]
    if left_state is not None:
        error_conditions.append(sx.OpExpr(sx.Operator.GE, left_state["max"], data))
        error_conditions.append(left_state["error"])
    if right_state is not None:
        error_conditions.append(sx.OpExpr(sx.Operator.LE, right_state["min"], data))
        error_conditions.append(right_state["error"])
    conditions.append(sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)))
    return sx.OpExpr(sx.Operator.AND, *conditions)


def not_psi_avl_struct(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The negation of the AVL structure of `psi_avl` without its bst check: `error` holds iff some node of the
    subtree has a `bal` field different from height(right) - height(left) or outside {-1, 0, 1}. A nil child has
    height 0. The height is computed for every subtree, so the relation is total."""
    left_state, right_state = children_states["left"], children_states["right"]
    left_height = left_state["height"] if left_state is not None else sx.Constant(0)
    right_height = right_state["height"] if right_state is not None else sx.Constant(0)
    bal = fields["bal"]
    error_conditions: list[sx.SExpr] = [
        sx.OpExpr(
            sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, bal, sx.OpExpr(sx.Operator.SUB, right_height, left_height))
        ),
        sx.OpExpr(sx.Operator.GT, bal, sx.Constant(1)),
        sx.OpExpr(sx.Operator.LT, bal, sx.Constant(-1)),
        *(state["error"] for state in (left_state, right_state) if state is not None),
    ]
    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.EQ, states["height"], sx.OpExpr(sx.Operator.ADD, sx.Max(left_height, right_height), 1)),
        sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)),
    )


def _psi_rb_template(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
    bst_psi: PsiType,
) -> sx.SExpr:
    """black_height counts the black nodes on every path down to nil, a nil child is black with black height 0.
    The colour of the node is its data field `red`."""
    red, black_height = states["red"], states["black_height"]
    children = [state for state in (children_states["left"], children_states["right"]) if state is not None]
    children_height = [state["black_height"] for state in children] + [sx.Constant(0)] * (2 - len(children))

    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.EQ, red, fields["red"]),
        sx.OpExpr(sx.Operator.EQ, children_height[0], children_height[1]),
        sx.OpExpr(
            sx.Operator.EQ,
            black_height,
            sx.OpExpr(
                sx.Operator.ADD, children_height[0], sx.OpExpr(sx.Operator.ITE, red, sx.Constant(0), sx.Constant(1))
            ),
        ),
        *(sx.OpExpr(sx.Operator.IMPLIES, red, sx.OpExpr(sx.Operator.NOT, state["red"])) for state in children),
        bst_psi(children_states, fields, states),
    )


def psi_rb(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    return _psi_rb_template(children_states, fields, states, psi_bst_strict)


def psi_rb_struct(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The red-black structure of `psi_rb` without its bst check: same black height on both children, no red node
    with a red child. The root being black is checked by `root_is_black`."""
    return _psi_rb_template(children_states, fields, states, psi_true)


def _rb_struct_parts(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> tuple[list[sx.SExpr], list[sx.SExpr]]:
    """The constraints on `red` and `black_height` of `not_psi_rb_struct` and the conditions of its error (the
    error of a child, a red node with a red child, children of different black heights)."""
    left_state, right_state = children_states["left"], children_states["right"]
    red = fields["red"]
    # a black node adds 1 to the black height, a red one 0
    own_height = sx.OpExpr(sx.Operator.ITE, red, sx.Constant(0), sx.Constant(1))
    # a nil child is black with black height 0
    left_height = left_state["black_height"] if left_state is not None else sx.Constant(0)
    right_height = right_state["black_height"] if right_state is not None else sx.Constant(0)
    conditions: list[sx.SExpr] = [
        sx.OpExpr(sx.Operator.EQ, states["red"], red),
        # the black height is taken from the left child only, so it is defined also when the two heights differ
        sx.OpExpr(sx.Operator.EQ, states["black_height"], sx.OpExpr(sx.Operator.ADD, left_height, own_height)),
    ]
    error_conditions: list[sx.SExpr] = [
        sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, left_height, right_height))
    ]
    for state in (left_state, right_state):
        if state is not None:
            # a red node has no red child
            error_conditions.append(sx.OpExpr(sx.Operator.AND, red, state["red"]))
            error_conditions.append(state["error"])
    return conditions, error_conditions


def not_psi_rb_struct(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The negation of the red-black structure of `psi_rb` without its bst check: `error` holds iff some node of the
    subtree has children of different black heights, or is red with a red child. A nil child is black with black
    height 0. The other states are computed for every subtree, so the relation is total; the root being red is
    checked by `rb_struct_error_psiF`."""
    conditions, error_conditions = _rb_struct_parts(children_states, fields, states)
    return sx.OpExpr(
        sx.Operator.AND,
        *conditions,
        sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)),
    )


def not_psi_rb(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The negation of `psi_rb`: `error` holds iff some node of the subtree breaks the red-black structure (see
    `not_psi_rb_struct`) or the strict bst order (a left key >= the node key, or a right key <= it). `min`/`max`
    are the extreme keys of the subtree, computed also when the order is broken, so the relation is total; the root
    being red is checked by `rb_struct_error_psiF`."""
    left_state, right_state = children_states["left"], children_states["right"]
    data = fields["data"]
    conditions, error_conditions = _rb_struct_parts(children_states, fields, states)
    if left_state is not None:
        error_conditions.append(sx.OpExpr(sx.Operator.GE, left_state["max"], data))
    if right_state is not None:
        error_conditions.append(sx.OpExpr(sx.Operator.LE, right_state["min"], data))
    return sx.OpExpr(
        sx.Operator.AND,
        *conditions,
        sx.OpExpr(sx.Operator.EQ, states["data"], data),
        sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"] if left_state is not None else data),
        sx.OpExpr(sx.Operator.EQ, states["max"], right_state["max"] if right_state is not None else data),
        sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)),
    )


def not_psi_rb_red(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The negation of "a red node has only black children": `error` holds iff some node of the subtree is red with
    a red child. A nil child is black. The relation is total."""
    red = fields["red"]
    children = [state for state in (children_states["left"], children_states["right"]) if state is not None]
    error_conditions: list[sx.SExpr] = [sx.FALSE]
    for child in children:
        error_conditions.append(sx.OpExpr(sx.Operator.AND, red, child["red"]))
        error_conditions.append(child["error"])
    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.EQ, states["red"], red),
        sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)),
    )


def not_psi_rb_black_height(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """The negation of "every path from a node down to nil has the same number of black nodes": `error` holds iff
    some node of the subtree has children of different black heights. A nil child has black height 0, a black node
    adds 1. The black height is taken from the left child, so the relation is total."""
    left_state, right_state = children_states["left"], children_states["right"]
    left_height = left_state["black_height"] if left_state is not None else sx.Constant(0)
    right_height = right_state["black_height"] if right_state is not None else sx.Constant(0)
    own_height = sx.OpExpr(sx.Operator.ITE, fields["red"], sx.Constant(0), sx.Constant(1))
    error_conditions: list[sx.SExpr] = [
        sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, left_height, right_height)),
        *(state["error"] for state in (left_state, right_state) if state is not None),
    ]
    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.EQ, states["black_height"], sx.OpExpr(sx.Operator.ADD, left_height, own_height)),
        sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)),
    )


def not_psi_rb_struct_height(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """`not_psi_rb_struct` with a height check in place of the black-height check: `error` holds iff some node of
    the subtree is red with a red child, or has a subtree more than twice as high as the other. Heights count the
    nil leaves (a nil child has height 1), so every red-black tree passes the check: a subtree with black height b
    has height between b + 1 and 2b + 2. The relation is total; the root being red is checked by
    `rb_struct_error_psiF`."""
    left_state, right_state = children_states["left"], children_states["right"]
    red = fields["red"]
    left_height = left_state["height"] if left_state is not None else sx.Constant(1)
    right_height = right_state["height"] if right_state is not None else sx.Constant(1)
    two = sx.Constant(2)
    error_conditions: list[sx.SExpr] = [
        sx.OpExpr(sx.Operator.GT, left_height, sx.OpExpr(sx.Operator.MUL, two, right_height)),
        sx.OpExpr(sx.Operator.GT, right_height, sx.OpExpr(sx.Operator.MUL, two, left_height)),
    ]
    for state in (left_state, right_state):
        if state is not None:
            error_conditions.append(sx.OpExpr(sx.Operator.AND, red, state["red"]))
            error_conditions.append(state["error"])
    return sx.OpExpr(
        sx.Operator.AND,
        sx.OpExpr(sx.Operator.EQ, states["red"], red),
        sx.OpExpr(sx.Operator.EQ, states["height"], sx.OpExpr(sx.Operator.ADD, sx.Max(left_height, right_height), 1)),
        sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions)),
    )


def not_psi_rb_root_black(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """Carries the colour of the node; with `root_is_red` as ψ_F it is the negation of "the root is black"."""
    return sx.OpExpr(sx.Operator.EQ, states["red"], fields["red"])


# def not_psi_rb(
#     children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
#     fields: Mapping[str, sx.SExpr],
#     enum_fields: dict[str, str],
#     states: Mapping[str, sx.SExpr]
# ) -> sx.SExpr:
#     conditions: list[sx.SExpr] = []
#     error_conditions: list[sx.SExpr] = []

#     left_state = children_states["left"]
#     right_state = children_states["right"]

#     conditions.append(sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]))

#     if left_state is None and right_state is None:
#         if enum_fields["color"] == "RED":
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["black_height"], sx.Constant(0)))
#         else: # enum_fields["color"] == "BLACK"
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["black_height"], sx.Constant(1)))
#         conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))
#         conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))

#     else:

#         if left_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(sx.OpExpr(sx.Operator.EQ, left_state["black_height"], states["black_height"]))
#                 error_conditions.append(sx.OpExpr(sx.Operator.GT, left_state["min"], states["data"]))
#             else: # BLACK
#                 conditions.append(
#                     sx.OpExpr(
#                         sx.Operator.EQ,
#                         sx.OpExpr(sx.Operator.ADD, left_state["black_height"], sx.Constant(1)),
#                         states["black_height"],
#                     )
#                 )
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"]))
#             error_conditions.append(left_state["error"])
#         else:
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], states["data"]))

#         if right_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(sx.OpExpr(sx.Operator.EQ, right_state["black_height"], states["black_height"]))
#                 error_conditions.append(sx.OpExpr(sx.Operator.LT, right_state["max"], states["data"]))
#             else: # BLACK
#                 conditions.append(
#                     sx.OpExpr(
#                         sx.Operator.EQ,
#                         sx.OpExpr(sx.Operator.ADD, right_state["black_height"], sx.Constant(1)),
#                         states["black_height"],
#                     )
#                 )
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], right_state["min"]))
#             error_conditions.append(right_state["error"])
#         else:
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], states["data"]))

#         left_height  = left_state["black_height"] if left_state is not None else sx.Constant(0)
#         right_height = right_state["black_height"] if right_state is not None else sx.Constant(0)
#         error_conditions.append(sx.OpExpr(sx.Operator.EQ, left_height, right_height))

#     error = sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions))
#     conditions.append(error)
#     return sx.OpExpr(sx.Operator.AND, *conditions)


# def psi_rb_strict(
#     children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
#     fields: Mapping[str, sx.SExpr],
#     enum_fields: dict[str, str],
#     states: Mapping[str, sx.SExpr]
# ) -> sx.SExpr:
#     return _psi_rb_template(children_states, fields, enum_fields, states, psi_bst_strict)


# def not_psi_rb_strict(
#     children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
#     fields: Mapping[str, sx.SExpr],
#     enum_fields: dict[str, str],
#     states: Mapping[str, sx.SExpr]
# ) -> sx.SExpr:
#     conditions: list[sx.SExpr] = []
#     error_conditions: list[sx.SExpr] = []

#     left_state = children_states["left"]
#     right_state = children_states["right"]

#     conditions.append(sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]))

#     if left_state is None and right_state is None:
#         if enum_fields["color"] == "RED":
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["black_height"], sx.Constant(0)))
#         else: # enum_fields["color"] == "BLACK"
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["black_height"], sx.Constant(1)))
#         conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], fields["data"]))
#         conditions.append(sx.OpExpr(sx.Operator.EQ, states["max"], fields["data"]))

#     else:

#         if left_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(sx.OpExpr(sx.Operator.EQ, left_state["black_height"], states["black_height"]))
#                 error_conditions.append(sx.OpExpr(sx.Operator.GT, left_state["min"], states["data"]))
#             else: # BLACK
#                 conditions.append(
#                     sx.OpExpr(
#                         sx.Operator.EQ,
#                         sx.OpExpr(sx.Operator.ADD, left_state["black_height"], sx.Constant(1)),
#                         states["black_height"],
#                     )
#                 )
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], left_state["min"]))
#             error_conditions.append(left_state["error"])
#         else:
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], states["data"]))

#         if right_state is not None:
#             if enum_fields["color"] == "RED":
#                 conditions.append(sx.OpExpr(sx.Operator.EQ, right_state["black_height"], states["black_height"]))
#                 error_conditions.append(sx.OpExpr(sx.Operator.LT, right_state["max"], states["data"]))
#             else: # BLACK
#                 conditions.append(
#                     sx.OpExpr(
#                         sx.Operator.EQ,
#                         sx.OpExpr(sx.Operator.ADD, right_state["black_height"], sx.Constant(1)),
#                         states["black_height"],
#                     )
#                 )
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], right_state["min"]))
#             error_conditions.append(right_state["error"])
#         else:
#             conditions.append(sx.OpExpr(sx.Operator.EQ, states["min"], states["data"]))

#         left_height  = left_state["black_height"] if left_state is not None else sx.Constant(0)
#         right_height = right_state["black_height"] if right_state is not None else sx.Constant(0)
#         error_conditions.append(sx.OpExpr(sx.Operator.EQ, left_height, right_height))

#     error = sx.OpExpr(sx.Operator.EQ, states["error"], sx.OpExpr(sx.Operator.OR, *error_conditions))
#     conditions.append(error)
#     return sx.OpExpr(sx.Operator.AND, *conditions)


def psi_true(
    children_states: Mapping[str, Mapping[str, sx.SExpr] | None],
    fields: Mapping[str, sx.SExpr],
    states: Mapping[str, sx.SExpr],
) -> sx.SExpr:
    """ψ of the automaton accepting every tree: it has no state to compute."""
    return sx.TRUE


def psiF_empty(states: Mapping[str, sx.SExpr]) -> sx.SExpr:  # noqa: N802
    return sx.TRUE


def error_psiF(states: Mapping[str, sx.SExpr]) -> sx.SExpr:  # noqa: N802
    return states["error"]

    # return sx.OpExpr(
    #     sx.Operator.AND,
    #     sx.OpExpr(sx.Operator.GE, children_states["next"]["data"], fields["data"]),
    #     sx.OpExpr(sx.Operator.EQ, states["data"], fields["data"]),
    # )


def root_is_black(states: Mapping[str, sx.SExpr]) -> sx.SExpr:
    return sx.OpExpr(sx.Operator.NOT, states["red"])


def root_is_red(states: Mapping[str, sx.SExpr]) -> sx.SExpr:
    return states["red"]


def rb_struct_error_psiF(states: Mapping[str, sx.SExpr]) -> sx.SExpr:  # noqa: N802
    """The negation of `root_is_black` on a tree without errors: an error below, or a red root."""
    return sx.OpExpr(sx.Operator.OR, states["error"], states["red"])
