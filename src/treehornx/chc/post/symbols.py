"""SMT symbols of the DFS CHC system.

The predicate of a DFS label ρ is `Dfs<ID>`. Its arguments are the arguments of the Lab predicate of the
complete Lab label σ of the node (`v<id>_<pos>`, `f<id>_<pos>`) and, when a postcondition is checked, the
automaton states held by the frames of ρ. DFS labels are not compressed: every frame b contributes, for each
slot whose flag is `Q()`, the symbols `post_ns_<STATE>_<b>` (node state), `post_cs<j>_<STATE>_<b>` (state of
the j-th child) and `post_rl_<STATE>_<b>` (relay). In clauses involving two nodes, every name is prefixed
with `s` for the sender σ and `t` for the receiver τ.
"""

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.chc.Lab.symbols import frame_types, kept_frames, label_symbols
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.enum_models.Dfs import Dfs, DfsFrame, Q, sigma_of

NODE_STATE = "ns"
RELAY = "rl"


def child_slot(j: int) -> str:
    return f"cs{j}"


def slot_flag(f: DfsFrame, slot: str) -> object:
    if slot == NODE_STATE:
        return f.node_state
    if slot == RELAY:
        return f.relay
    return f.child_state[int(slot.removeprefix("cs"))]


def frame_slots(f: DfsFrame) -> list[str]:
    """Slots of the frame holding an automaton state."""
    slots = [child_slot(j) for j, state in enumerate(f.child_state) if state == Q()]
    if f.node_state == Q():
        slots.insert(0, NODE_STATE)
    if f.relay == Q():
        slots.append(RELAY)
    return slots


def state_type(ctx: SDTAContext, state: str) -> smtty.PySMTType:
    return smtty.INT if ctx.states[state] == "int" else smtty.BOOL


def state_symbols(ctx: SDTAContext, slot: str, b: int, prefix: str = "") -> dict[str, FNode]:
    return {state: smt.Symbol(f"{prefix}post_{slot}_{state}_{b}", state_type(ctx, state)) for state in ctx.states}


def dfs_label_symbols(function: ir.Function, ctx: SDTAContext | None, rho: Dfs, prefix: str = "") -> list[FNode]:
    symbols = label_symbols(function, sigma_of(rho), prefix)
    if ctx is not None:
        for b in range(1, len(rho) + 1):
            for slot in frame_slots(rho[b]):
                symbols.extend(state_symbols(ctx, slot, b, prefix).values())
    return symbols


def dfs_arg_types(function: ir.Function, ctx: SDTAContext | None, rho: Dfs) -> list[smtty.PySMTType]:
    types = [t for _ in kept_frames(sigma_of(rho)) for t in frame_types(function)]
    if ctx is not None:
        for b in range(1, len(rho) + 1):
            for _ in frame_slots(rho[b]):
                types.extend(state_type(ctx, state) for state in ctx.states)
    return types


def dfs_predicate(function: ir.Function, ctx: SDTAContext | None, rho: Dfs) -> FNode:
    return chc.Predicate(f"Dfs{rho.id}", dfs_arg_types(function, ctx, rho))


def dfs_apply(function: ir.Function, ctx: SDTAContext | None, rho: Dfs, prefix: str = "") -> FNode:
    return chc.Apply(dfs_predicate(function, ctx, rho), dfs_label_symbols(function, ctx, rho, prefix))
