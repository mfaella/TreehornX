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
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.enum_models.core.Dir import Down, Up
from treehornx.enum_models.Lab import ERR, Lab
from treehornx.enum_models.Lab.helpers import are_equal_after_rewind, field_is_nil
from treehornx.enum_models.Lab.initial import is_initial

SIGMA_PREFIX = "s"
TAU_PREFIX = "t"


def _clause(constraints: list[FNode], head: FNode) -> FNode:
    return chc.Clause(smt.And(*constraints), head) if constraints else head


def linked_frames(parent: Lab, child: Lab, j: int) -> list[tuple[int, int]]:
    """Pairs (i, c) such that the frame parent^i and the frame child^c of its j-th child are adjacent in the lace.

    Only links between the two nodes count: a parent frame reached by Up comes from the grandparent, a child
    frame reached by Down(j') from a grandchild, and a parent frame reached by Down(j') from another child."""
    links: list[tuple[int, int]] = []
    for c in range(2, len(child) + 1):
        match child[c].prev:
            case (Up(), i) if 1 <= i <= len(parent):
                links.append((i, c))
            case _:
                pass
    for i in range(2, len(parent) + 1):
        match parent[i].prev:
            case (Down(j_), c) if j_ == j and 1 <= c <= len(child):
                links.append((i, c))
            case _:
                pass
    return links


def consistency_constraint(
    sym: ChcLabUtils, parent: Lab, child: Lab, j: int, parent_prefix: str = "", child_prefix: str = ""
) -> FNode:
    """The data variables agree on every pair of frames of the parent and its j-th child adjacent in the lace."""
    return smt.And(
        *(
            smt.EqualsOrIff(left, right)
            for i, c in linked_frames(parent, child, j)
            for left, right in zip(sym.var_symbols(i, parent_prefix), sym.var_symbols(c, child_prefix))
        )
    )


def fact(sym: ChcLabUtils, label: Lab) -> FNode:
    """CHC I (non-root nodes) and CHC II (root): the root's second frame copies val from the first."""
    constraints: list[FNode] = []
    if is_initial(label):
        constraints = [
            smt.EqualsOrIff(f2, f1) for f2, f1 in zip(sym.field_symbols(2), sym.field_symbols(1))
        ]
    return _clause(constraints, sym.apply(label))


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
        case ir.FieldIsNil(_, pfield, neg):
            # p points to the node holding label^a, otherwise the step dereferences nil or rewinds
            return field_is_nil(label.cut(a), a, pfield) != neg


def psi_internal(sym: ChcLabUtils, label: Lab) -> list[FNode]:
    """Data constraints of the internal step from label^{b-1} to the top frame label^b."""
    b = len(label)
    a = b - 1
    f_a, f_b = label[a], label[b]
    vars_value: dict[int, FNode] = {}
    fields_value: dict[int, FNode] = {}
    constraints: list[FNode] = []

    match sym.function[f_a.pc]:
        case ir.AssignData(d, expr):
            vars_value[d] = sym.expr_to_smt(expr, a)
        case ir.AssignCond(d, cond) if not isinstance(f_b.event, ERR):
            vars_value[d] = smt.Bool(_assign_cond_value(label, a, cond))
        case ir.IfGoto(ir.DataCond(expr), target) if target != f_a.pc + 1:
            cond = sym.expr_to_smt(expr, a)
            constraints.append(cond if f_b.pc == target else smt.Not(cond))
        case ir.StoreDataField(_, field, value) if not isinstance(f_b.event, ERR):
            fields_value[field] = sym.expr_to_smt(value, a)
        case ir.LoadDataField(d, _, field) if not isinstance(f_b.event, ERR):
            vars_value[d] = sym.field_symbol(field, a)
        case _:
            pass

    for v in sym.function.data_vars:
        value = vars_value.get(v.id, sym.var_symbol(v.id, a))
        constraints.append(smt.EqualsOrIff(sym.var_symbol(v.id, b), value))
    for fd in sym.function.node.data_fields:
        value = fields_value.get(fd.id, sym.field_symbol(fd.id, a))
        constraints.append(smt.EqualsOrIff(sym.field_symbol(fd.id, b), value))
    return constraints


def internal_clause(sym: ChcLabUtils, label: Lab) -> FNode:
    """CHC III, compressed: the frame label^{b-1} is dropped from the head if it is in the middle of an
    internal chain."""
    assert label.prefix is not None
    return _clause([sym.apply(label.prefix), *psi_internal(sym, label)], sym.apply(label))


def external_clause(sym: ChcLabUtils, receiver: Lab, sender: Lab, j: int) -> FNode:
    """CHC IV/V: the top frame of `receiver` (τ) follows in the lace the top frame of `sender` (σ), one of
    them being the j-th child of the other.

    The data variables are copied from σ^a by the consistency constraint (which includes the new
    link), the data fields are copied from τ^{b-1}, the frame below in the same node."""
    assert receiver.prefix is not None
    b = len(receiver)
    fields_below = [
        smt.EqualsOrIff(f_b, f_below)
        for f_b, f_below in zip(sym.field_symbols(b, TAU_PREFIX), sym.field_symbols(b - 1, TAU_PREFIX))
    ]
    body = [
        sym.apply(receiver.prefix, TAU_PREFIX),
        sym.apply(sender, SIGMA_PREFIX),
        consistency(sym, receiver, sender, j),
        *fields_below,
    ]
    return _clause(body, sym.apply(receiver, TAU_PREFIX))


def consistency(sym: ChcLabUtils, receiver: Lab, sender: Lab, j: int) -> FNode:
    """consistency_constraint between τ and σ, oriented by the direction of the link of τ's top frame."""
    match receiver.frame.prev:
        case (Up(), _):
            return consistency_constraint(sym, sender, receiver, j, SIGMA_PREFIX, TAU_PREFIX)
        case _:
            return consistency_constraint(sym, receiver, sender, j, TAU_PREFIX, SIGMA_PREFIX)


def query(sym: ChcLabUtils, label: Lab) -> FNode:
    return chc.Clause(sym.apply(label), smt.FALSE())
