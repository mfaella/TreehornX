"""Clauses of the Lab CHC system (CAV25, Fig. 3), restricted to the data part of the frames.

The shape part is fixed by the enumerated labels, so every clause only constrains the data
symbols (see `symbols.py`). In external clauses the symbols of σ, the label holding the frame
the lace comes from, are prefixed with `s`, those of τ, the label receiving the new frame, with
`t`.
"""

import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.clean import clean_clause
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.enum_models.core.Dir import Internal, Up
from treehornx.enum_models.Lab import ERR, Lab
from treehornx.enum_models.Lab.helpers import are_equal_after_rewind, field_is_nil, linked_frames
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.feature_flags import FeatureFlags


SIGMA_PREFIX = "s"
TAU_PREFIX = "t"


def _clause(constraints: list[FNode], head: FNode, clean: bool) -> FNode | None:
    return clean_clause(constraints, head, clean)


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


def initial_constraints(sym: ChcLabUtils, prefix: str = "") -> list[FNode]:
    """The root's second frame copies val from the first (CHC II)."""
    return [smt.EqualsOrIff(f2, f1) for f2, f1 in zip(sym.field_symbols(2, prefix), sym.field_symbols(1, prefix))]


def fact(sym: ChcLabUtils, label: Lab, flags: FeatureFlags) -> FNode | None:
    """CHC I (non-root nodes) and CHC II (root): the root's second frame copies val from the first."""
    return _clause(_head_constraints(sym, label, flags.lab_internal_constraints), sym.apply(label), flags.clean_clause)


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


def psi_internal(sym: ChcLabUtils, label: Lab, prefix: str = "") -> list[FNode]:
    """Data constraints of the internal step from label^{b-1} to the top frame label^b."""
    b = len(label)
    a = b - 1
    f_a, f_b = label[a], label[b]
    vars_value: dict[int, FNode] = {}
    fields_value: dict[int, FNode] = {}
    constraints: list[FNode] = []

    match sym.function[f_a.pc]:
        case ir.AssignData(d, expr):
            vars_value[d] = sym.expr_to_smt(expr, a, prefix)
        case ir.AssignCond(d, cond) if not isinstance(f_b.event, ERR):
            vars_value[d] = smt.Bool(_assign_cond_value(label, a, cond))
        case ir.IfGoto(ir.DataCond(expr), target) if target != f_a.pc + 1:
            cond = sym.expr_to_smt(expr, a, prefix)
            constraints.append(cond if f_b.pc == target else smt.Not(cond))
        case ir.StoreDataField(_, field, value) if not isinstance(f_b.event, ERR):
            fields_value[field] = sym.expr_to_smt(value, a, prefix)
        case ir.LoadDataField(d, _, field) if not isinstance(f_b.event, ERR):
            vars_value[d] = sym.field_symbol(field, a, prefix)
        case _:
            pass

    for v in sym.function.data_vars:
        value = vars_value.get(v.id, sym.var_symbol(v.id, a, prefix))
        constraints.append(smt.EqualsOrIff(sym.var_symbol(v.id, b, prefix), value))
    for fd in sym.function.node.data_fields:
        value = fields_value.get(fd.id, sym.field_symbol(fd.id, a, prefix))
        constraints.append(smt.EqualsOrIff(sym.field_symbol(fd.id, b, prefix), value))
    return constraints


def _local_constraints(sym: ChcLabUtils, label: Lab, prefix: str) -> list[FNode]:
    """Constraints of the internal step reaching the top frame of `label`, if any."""
    if label.frame.prev != Internal():
        return []
    if len(label) == 2 and is_initial(label):
        # (Internal(), 2) marks the second frame of the root, it is not a step of the program
        return initial_constraints(sym, prefix)
    return psi_internal(sym, label, prefix)


def internal_constraints(sym: ChcLabUtils, label: Lab, prefix: str = "") -> list[FNode]:
    """Constraints of every internal step of `label`, including those between frames dropped from its predicate.

    The frames dropped by the compression only occur here, so they are quantified variables of the clause."""
    cache = sym.internal_constraints_cache
    # walk back to the longest prefix already computed, then extend it frame by frame
    missing: list[Lab] = []
    current: Lab | None = label
    while current is not None and (current, prefix) not in cache:
        missing.append(current)
        current = current.prefix
    cached = () if current is None else cache[current, prefix]
    for prefix_label in reversed(missing):
        cached = cached + tuple(_local_constraints(sym, prefix_label, prefix))
        cache[prefix_label, prefix] = cached
    return list(cached)


def _head_constraints(sym: ChcLabUtils, label: Lab, every_step: bool) -> list[FNode]:
    """Constraints of the head label: only the step to its top frame, unless every internal step is added."""
    return internal_constraints(sym, label) if every_step else _local_constraints(sym, label, "")


def _body_constraints(sym: ChcLabUtils, label: Lab, every_step: bool, prefix: str = "") -> list[FNode]:
    """Constraints of a body label, already enforced by the clauses deriving it unless every internal step is added."""
    return internal_constraints(sym, label, prefix) if every_step else []


def internal_clause(sym: ChcLabUtils, label: Lab, flags: FeatureFlags) -> FNode | None:
    """CHC III, compressed: the frame label^{b-1} is dropped from the head if it is in the middle of an
    internal chain. The constraints of the label include the step to its top frame."""
    assert label.prefix is not None
    head_constraints = _head_constraints(sym, label, flags.lab_internal_constraints)
    return _clause([sym.apply(label.prefix), *head_constraints], sym.apply(label), flags.clean_clause)


def external_clause(sym: ChcLabUtils, receiver: Lab, sender: Lab, j: int, flags: FeatureFlags) -> FNode | None:
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
        *_body_constraints(sym, receiver, flags.lab_internal_constraints, TAU_PREFIX),
        *_body_constraints(sym, sender, flags.lab_internal_constraints, SIGMA_PREFIX),
    ]
    return _clause(body, sym.apply(receiver, TAU_PREFIX), flags.clean_clause)


def consistency(sym: ChcLabUtils, receiver: Lab, sender: Lab, j: int) -> FNode:
    """consistency_constraint between τ and σ, oriented by the direction of the link of τ's top frame."""
    match receiver.frame.prev:
        case Up():
            return consistency_constraint(sym, sender, receiver, j, SIGMA_PREFIX, TAU_PREFIX)
        case _:
            return consistency_constraint(sym, receiver, sender, j, TAU_PREFIX, SIGMA_PREFIX)


def query(sym: ChcLabUtils, label: Lab, flags: FeatureFlags) -> FNode | None:
    body = [sym.apply(label), *_body_constraints(sym, label, flags.lab_internal_constraints)]
    return _clause(body, smt.FALSE(), flags.clean_clause)
