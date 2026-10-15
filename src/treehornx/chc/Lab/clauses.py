"""Clauses of the Lab CHC system (CAV25, Fig. 3), restricted to the data part of the frames.

The shape part is fixed by the enumerated labels, so every clause only constrains the data
symbols (see `symbols.py`). In external clauses the symbols of σ, the label holding the frame
the lace comes from, are prefixed with `s`, those of τ, the label receiving the new frame, with
`t`.
"""

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.symbols import apply, expr_to_smt, field_symbol, field_symbols, var_symbol, var_symbols
from treehornx.enum_models.core.Dir import Internal, are_opposite_directions
from treehornx.enum_models.Lab import ERR, Lab
from treehornx.enum_models.Lab.helpers import are_equal_after_rewind, next_of, prev_of
from treehornx.enum_models.Lab.initial import is_initial

SIGMA_PREFIX = "s"
TAU_PREFIX = "t"


def _clause(constraints: list[FNode], head: FNode) -> FNode:
    return chc.Clause(smt.And(*constraints), head) if constraints else head


def linked_frames(l1: Lab, l2: Lab) -> list[tuple[int, int]]:
    """Pairs (i, c) such that the frame l1^i and the frame l2^c are adjacent in the lace."""
    links: list[tuple[int, int]] = []
    for receiver, sender, swap in ((l1, l2, False), (l2, l1, True)):
        for i in range(2, len(receiver) + 1):
            prev = prev_of(receiver, i)
            if prev is None or prev[0] == Internal() or not 1 <= prev[1] <= len(sender):
                continue
            nxt = next_of(sender, prev[1])
            if nxt is not None and nxt[1] == i and are_opposite_directions(prev[0], nxt[0]):
                links.append((prev[1], i) if swap else (i, prev[1]))
    return links


def consistency_constraint(function: ir.Function, l1: Lab, l2: Lab, prefix1: str = "", prefix2: str = "") -> FNode:
    """The data variables agree on every pair of frames of l1 and l2 that are adjacent in the lace."""
    return smt.And(
        *(
            smt.EqualsOrIff(left, right)
            for i, c in linked_frames(l1, l2)
            for left, right in zip(var_symbols(function, i, prefix1), var_symbols(function, c, prefix2))
        )
    )


def fact(function: ir.Function, label: Lab) -> FNode:
    """CHC I (non-root nodes) and CHC II (root): the root's second frame copies val from the first."""
    constraints: list[FNode] = []
    if is_initial(label):
        constraints = [
            smt.EqualsOrIff(f2, f1) for f2, f1 in zip(field_symbols(function, 2), field_symbols(function, 1))
        ]
    return _clause(constraints, apply(function, label))


def _assign_cond_value(label: Lab, a: int, cond: ir.HeapCond) -> bool:
    """Value of the heap condition evaluated by the internal step leaving the frame label^a."""
    f = label[a]
    match cond:
        case ir.IsNil(p, neg):
            return f.isnil[p] != neg
        case ir.PtrEq(p, q, neg):
            if f.isnil[p] or f.isnil[q]:
                return (f.isnil[p] == f.isnil[q]) != neg
            return are_equal_after_rewind(label.cut(a), a, p, q) != neg


def psi_internal(function: ir.Function, label: Lab) -> list[FNode]:
    """Data constraints of the internal step from label^{b-1} to the top frame label^b."""
    b = len(label)
    a = b - 1
    f_a, f_b = label[a], label[b]
    vars_value: dict[int, FNode] = {}
    fields_value: dict[int, FNode] = {}
    constraints: list[FNode] = []

    match function[f_a.pc]:
        case ir.AssignData(d, expr):
            vars_value[d] = expr_to_smt(function, expr, a)
        case ir.AssignCond(d, cond):
            vars_value[d] = smt.Bool(_assign_cond_value(label, a, cond))
        case ir.IfGoto(ir.DataCond(expr), target) if target != f_a.pc + 1:
            cond = expr_to_smt(function, expr, a)
            constraints.append(cond if f_b.pc == target else smt.Not(cond))
        case ir.StoreDataField(_, field, value) if not isinstance(f_b.event, ERR):
            fields_value[field] = expr_to_smt(function, value, a)
        case ir.LoadDataField(d, _, field) if not isinstance(f_b.event, ERR):
            vars_value[d] = field_symbol(function, field, a)
        case _:
            pass

    for v in function.data_vars:
        value = vars_value.get(v.id, var_symbol(function, v.id, a))
        constraints.append(smt.EqualsOrIff(var_symbol(function, v.id, b), value))
    for fd in function.node.data_fields:
        value = fields_value.get(fd.id, field_symbol(function, fd.id, a))
        constraints.append(smt.EqualsOrIff(field_symbol(function, fd.id, b), value))
    return constraints


def internal_clause(function: ir.Function, label: Lab) -> FNode:
    """CHC III, compressed: the frame label^{b-1} is dropped from the head if it is in the middle of an
    internal chain."""
    assert label.prefix is not None
    return _clause([apply(function, label.prefix), *psi_internal(function, label)], apply(function, label))


def external_clause(function: ir.Function, receiver: Lab, sender: Lab) -> FNode:
    """CHC IV/V: the top frame of `receiver` (τ) follows in the lace the top frame of `sender` (σ).

    The data variables are copied from σ^a by the consistency constraint (which includes the new
    link), the data fields are copied from τ^{b-1}, the frame below in the same node."""
    assert receiver.prefix is not None
    b = len(receiver)
    fields_below = [
        smt.EqualsOrIff(f_b, f_below)
        for f_b, f_below in zip(field_symbols(function, b, TAU_PREFIX), field_symbols(function, b - 1, TAU_PREFIX))
    ]
    body = [
        apply(function, receiver.prefix, TAU_PREFIX),
        apply(function, sender, SIGMA_PREFIX),
        consistency_constraint(function, receiver, sender, TAU_PREFIX, SIGMA_PREFIX),
        *fields_below,
    ]
    return _clause(body, apply(function, receiver, TAU_PREFIX))


def query(function: ir.Function, label: Lab) -> FNode:
    return chc.Clause(apply(function, label), smt.FALSE())
