"""Auxiliary predicates of the DFS lace (dfs_formulas, POPL App. E for the final value of pointer fields).

The Lab side is evaluated on the complete Lab label σ of a node, stored in the first frame of its DFS
label, at its last position |σ|.
"""

from typing import Callable

from treehornx import ir
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.Dfs.Event import NOP, RemoteTaint, StructTaint
from treehornx.enum_models.Dfs.Flag import Bot, StateNil
from treehornx.enum_models.Dfs.Frame import DfsFrame, MutableDfsFrame
from treehornx.enum_models.Dfs.Inst import Inst, Trans, VisitNext
from treehornx.enum_models.Lab.Frame import Frame
from treehornx.enum_models.Lab.helpers import get_pfield_ptr, is_pfield_implicit, is_pfield_nil

type Lab = Label[Frame]
type Dfs = Label[DfsFrame]

# ---------------------------------------------------------------------------
# Lab side: final value of the pointer fields
# ---------------------------------------------------------------------------


def sigma_of(rho: Dfs) -> Lab:
    sigma = rho[1].sigma
    assert sigma is not None, "the first frame of a DFS label holds its Lab label"
    return sigma


def child_is_dflt(sigma: Lab, j: int) -> bool:
    """No explicit assignment to the pointer field j is present in σ."""
    return is_pfield_implicit(sigma, len(sigma), j)


def child_is_struct(sigma: Lab, j: int) -> bool:
    """The j-th field still points to the j-th child of the input tree (even if it was freed)."""
    return child_is_dflt(sigma, j) and sigma[1].active_child[j]


def child_is_nil(sigma: Lab, j: int) -> bool:
    return (child_is_dflt(sigma, j) and not sigma[1].active_child[j]) or is_pfield_nil(sigma, len(sigma), j)


def child_is_ptr(sigma: Lab, j: int) -> tuple[int, int] | None:
    """(p, i) such that the last assignment to the j-th field is ⟨pf_j := p⟩ at the Lab position i."""
    return get_pfield_ptr(sigma, len(sigma), j)


def active(sigma: Lab) -> bool:
    """The node is active at the end of the execution."""
    return sigma.frame.active


def clean_end(function: ir.Function, sigma: Lab) -> bool:
    """The top frame of σ is the end of a lace that terminated at `exit`."""
    return sigma.next is None and len(sigma) >= 2 and isinstance(function[sigma.frame.pc], ir.Exit)


# ---------------------------------------------------------------------------
# DFS side
# ---------------------------------------------------------------------------


def first_unvstd_child(child_state: tuple[StateNil, ...] | list[StateNil]) -> int | None:
    return next((j for j, state in enumerate(child_state) if state == Bot()), None)


def visit_or_trans(j: int, k: int) -> Inst:
    return VisitNext() if j < k - 1 else Trans()


def struct_tainted(rho: Dfs, a: int) -> bool:
    return any(f.event == StructTaint() for f in rho[2 : a + 1])


def remote_tainted(rho: Dfs, a: int) -> int | None:
    """Position of the frame where the node was reached through a taint forwarding."""
    return next((r for r in range(2, a + 1) if rho[r].event == RemoteTaint()), None)


# ---------------------------------------------------------------------------
# Default values (default^P)
# ---------------------------------------------------------------------------


def default_node_state(fprev: DfsFrame, fbelow: DfsFrame, f: MutableDfsFrame) -> None:
    f.node_state = fbelow.node_state


def default_child_state(fprev: DfsFrame, fbelow: DfsFrame, f: MutableDfsFrame) -> None:
    f.child_state = list(fbelow.child_state)


def default_event(fprev: DfsFrame, fbelow: DfsFrame, f: MutableDfsFrame) -> None:
    f.event = NOP()


def default_inst(fprev: DfsFrame, fbelow: DfsFrame, f: MutableDfsFrame) -> None:
    f.inst = fprev.inst


def default_relay(fprev: DfsFrame, fbelow: DfsFrame, f: MutableDfsFrame) -> None:
    f.relay = fprev.relay


_DEFAULTS: dict[str, Callable[[DfsFrame, DfsFrame, MutableDfsFrame], None]] = {
    "node_state": default_node_state,
    "child_state": default_child_state,
    "event": default_event,
    "inst": default_inst,
    "relay": default_relay,
}


def default(*fields: str) -> Callable[[DfsFrame, DfsFrame, MutableDfsFrame], MutableDfsFrame]:
    """default^P_{fields}(fprev, fbelow, f)"""
    unknown = set(fields) - _DEFAULTS.keys()
    assert not unknown, f"Invalid default fields {unknown}. Valid fields are: {', '.join(_DEFAULTS)}"

    def _default(fprev: DfsFrame, fbelow: DfsFrame, f: MutableDfsFrame) -> MutableDfsFrame:
        for name in fields:
            _DEFAULTS[name](fprev, fbelow, f)
        return f

    return _default
