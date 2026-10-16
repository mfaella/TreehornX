"""Clauses of the DFS CHC system (notes/dfs_formulas, The CHC system).

Without an automaton (`ctx is None`) the clauses only check that the output heap is a tree: the predicates
carry the Lab data of the node. With an automaton, the predicates also carry the states, every new frame
receives its states from the frame they come from (`transfer`) and the automaton constraints ψ and ψ_F are
added where the automaton runs.
"""

from typing import Any, cast

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.clauses import consistency_constraint, linked_frames
from treehornx.chc.Lab.symbols import apply as lab_apply
from treehornx.chc.Lab.symbols import field_symbol
from treehornx.chc.post.symbols import NODE_STATE, RELAY, child_slot, dfs_apply, frame_slots, slot_flag, state_symbols
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.Dfs import (
    SFWD,
    TREE_ERRORS,
    Acc,
    Dfs,
    NOP,
    PushState,
    Q,
    RemoteTaint,
    StateForward,
    Trans,
    sigma_of,
)
from treehornx.enum_models.Dfs.helpers import first_unvstd_child
from treehornx.enum_models.Lab import Lab
from treehornx.enum_models.Lab.helpers import prev_of

SIGMA_PREFIX = "s"
TAU_PREFIX = "t"

type Slot = tuple[Dfs, int, str, str]
"""A state slot: (label, position, prefix of its symbols, slot name)."""


def _clause(constraints: list[FNode], head: FNode) -> FNode:
    return chc.Clause(smt.And(*constraints), head) if constraints else head


def _equal_states(ctx: SDTAContext, target: Slot, source: Slot) -> list[FNode]:
    (t_label, t_pos, t_prefix, t_slot), (s_label, s_pos, s_prefix, s_slot) = target, source
    assert slot_flag(s_label[s_pos], s_slot) == Q(), f"the state of {t_slot} comes from {s_slot}, which is not Q"
    targets = state_symbols(ctx, t_slot, t_pos, t_prefix)
    sources = state_symbols(ctx, s_slot, s_pos, s_prefix)
    return [smt.EqualsOrIff(targets[state], sources[state]) for state in ctx.states]


def transfer(
    function: ir.Function,
    ctx: SDTAContext,
    receiver: Dfs,
    b: int,
    sender: Dfs,
    a: int,
    receiver_prefix: str = "",
    sender_prefix: str = "",
) -> list[FNode]:
    """States of the frame receiver^b, which follows sender^a in the DFS lace.

    By default node and child states come from the frame below, the relay from the previous frame
    (default^P); the steps moving a state override the source of the slot they write."""
    new, fprev, fbelow = receiver[b], sender[a], receiver[b - 1]
    prev: tuple[Dfs, int, str] = (sender, a, sender_prefix)
    below: tuple[Dfs, int, str] = (receiver, b - 1, receiver_prefix)
    sources: dict[str, Slot | None] = {NODE_STATE: (*below, NODE_STATE), RELAY: (*prev, RELAY)}
    sources |= {child_slot(j): (*below, child_slot(j)) for j in range(len(new.child_state))}
    constraints: list[FNode] = []

    match fprev.inst, new.event:
        case Trans(), _:
            # automaton_transition: the node state is computed by ψ
            sources[NODE_STATE] = None
            children_states = {
                function.node.pointer_fields[j].name: (
                    state_symbols(ctx, child_slot(j), a, sender_prefix) if state == Q() else None
                )
                for j, state in enumerate(fprev.child_state)
            }
            sigma_lab = sigma_of(receiver)
            fields = {
                fd.name: field_symbol(function, fd.id, len(sigma_lab), receiver_prefix)
                for fd in function.node.data_fields
            }
            constraints.append(ctx.psi(children_states, fields, state_symbols(ctx, NODE_STATE, b, receiver_prefix)))
        case _, Acc():
            # step_accept: the automaton accepts the state of the root
            constraints.append(ctx.psiF(state_symbols(ctx, NODE_STATE, a, sender_prefix)))
        case _, RemoteTaint():
            sources[NODE_STATE] = (*prev, RELAY)
        case PushState(), SFWD():
            sources[RELAY] = (*prev, NODE_STATE)
        case PushState(), NOP():
            j = first_unvstd_child(fbelow.child_state)
            assert j is not None
            sources[child_slot(j)] = (*prev, NODE_STATE)
        case StateForward(), NOP():
            j = first_unvstd_child(fprev.child_state)
            assert j is not None
            sources[child_slot(j)] = (*prev, RELAY)
        case _:
            pass

    for slot in frame_slots(new):
        source = sources[slot]
        if source is not None:
            constraints.extend(_equal_states(ctx, (receiver, b, receiver_prefix, slot), source))
    return constraints


def dfs_consistency(function: ir.Function, ctx: SDTAContext, l1: Dfs, l2: Dfs, prefix1: str, prefix2: str) -> FNode:
    """The states moved by every step between frames of l1 and l2 adjacent in the DFS lace."""
    constraints: list[FNode] = []
    for i, c in linked_frames(cast(Any, l1), cast(Any, l2)):
        prev = prev_of(l1, i)
        if prev is not None and prev[0] != Internal() and prev[1] == c:
            constraints.extend(transfer(function, ctx, l1, i, l2, c, prefix1, prefix2))
        else:
            constraints.extend(transfer(function, ctx, l2, c, l1, i, prefix2, prefix1))
    return smt.And(*constraints)


def fact(function: ir.Function, ctx: SDTAContext | None, rho: Dfs) -> FNode:
    """I^P: the first frame of the DFS label of a node with a complete Lab label."""
    return chc.Clause(lab_apply(function, sigma_of(rho)), dfs_apply(function, ctx, rho))


def internal_clause(function: ir.Function, ctx: SDTAContext | None, rho: Dfs) -> FNode:
    """II^P"""
    assert rho.prefix is not None
    b = len(rho)
    constraints = [dfs_apply(function, ctx, rho.prefix)]
    if ctx is not None:
        constraints.extend(transfer(function, ctx, rho, b, rho, b - 1))
    return _clause(constraints, dfs_apply(function, ctx, rho))


def external_clause(function: ir.Function, ctx: SDTAContext | None, receiver: Dfs, sender: Dfs) -> FNode:
    """III^P / IV^P: the top frame of `receiver` (τ) follows the top frame of `sender` (σ) on the parent or a
    child; the Lab data and the states agree on every pair of linked frames."""
    assert receiver.prefix is not None
    constraints = [
        dfs_apply(function, ctx, receiver.prefix, TAU_PREFIX),
        dfs_apply(function, ctx, sender, SIGMA_PREFIX),
        consistency_constraint(function, sigma_of(receiver), sigma_of(sender), TAU_PREFIX, SIGMA_PREFIX),
    ]
    if ctx is not None:
        constraints.append(dfs_consistency(function, ctx, receiver, sender, TAU_PREFIX, SIGMA_PREFIX))
    return _clause(constraints, dfs_apply(function, ctx, receiver, TAU_PREFIX))


def is_violation(ctx: SDTAContext | None, rho: Dfs) -> bool:
    """V^P: the DFS lace ends with an error, with the acceptance of the (negated) postcondition when checked."""
    errors = TREE_ERRORS if ctx is None else (*TREE_ERRORS, Acc)
    return rho.next is None and isinstance(rho.frame.event, errors)


def is_overflow(n_dfs: int, rho: Dfs) -> bool:
    """The DFS label uses its last frame n_dfs + 1: the visit needs more frames than the bound allows."""
    return len(rho) == n_dfs + 1


def query(function: ir.Function, ctx: SDTAContext | None, rho: Dfs) -> FNode:
    return chc.Clause(dfs_apply(function, ctx, rho), smt.FALSE())


def empty_output_query(function: ir.Function, sigma: Lab) -> FNode:
    """SQ2: the lace ends at `exit` with an empty output tree, accepted by the (negated) postcondition."""
    return chc.Clause(lab_apply(function, sigma), smt.FALSE())
