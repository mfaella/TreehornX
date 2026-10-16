"""Symbolic engine of the DFS lace (notes/dfs_formulas).

The DFS lace runs on a complete knitted-tree: it visits the output heap depth first starting from the
final value of the root pointer variable, runs the automaton bottom-up and detects the output heaps that
are not trees. Steps follow the conventions of `LabEngine`:

* `_int`  the new frame extends the same label;
* `_down` the new frame is pushed on a child for sure;
* `_up`   the new frame is pushed on the parent for sure;
* `_ext`  the new frame is pushed on the parent or on a child, depending on the lace being followed.

σ is the DFS label holding the last frame of the lace (a = len(σ)), τ the DFS label receiving the new
frame (b = len(τ) + 1); σ_lab and τ_lab are the complete Lab labels of the two nodes.
"""

from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable, override

from treehornx import ir
from treehornx.enum_models.core.Dir import Dir, Down, Internal, Up, are_opposite_directions
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.core.SymbolicEngine import SymbolicEngine
from treehornx.enum_models.Dfs.Event import (
    ERR_EVENTS,
    SFWD,
    TFWD,
    Acc,
    Conv,
    Dang,
    Event,
    InitTFWD,
    Loop,
    RemoteTaint,
    SelfLoop,
    StructTaint,
)
from treehornx.enum_models.Dfs.Flag import Bot, Nil, Q, Top, Topp
from treehornx.enum_models.Dfs.Frame import DfsFrame, MutableDfsFrame
from treehornx.enum_models.Dfs.helpers import (
    Dfs,
    active,
    child_is_nil,
    child_is_ptr,
    child_is_struct,
    default,
    first_unvstd_child,
    remote_tainted,
    sigma_of,
    struct_tainted,
    visit_or_trans,
)
from treehornx.enum_models.Dfs.Inst import (
    Accept,
    FindP,
    NoInst,
    PushState,
    StateForward,
    Trans,
    VisitNext,
)
from treehornx.enum_models.Lab.helpers import last_upd, next_of, points_here, prev_of


@dataclass
class DfsEngine(SymbolicEngine[DfsFrame]):
    function: ir.Function = field(kw_only=True)

    @cached_property
    def num_ptrs(self) -> int:
        return len(self.function.pointer_vars)

    # -----------------------------------------------------------------------
    # SymbolicEngine interface
    # -----------------------------------------------------------------------

    @staticmethod
    def continues(f: DfsFrame) -> bool:
        """continues^P: the frame is not an error and has an instruction to execute."""
        return not isinstance(f.event, ERR_EVENTS) and f.inst != NoInst()

    @override
    def is_continuos(self, label: Dfs) -> bool:
        return label.next is None and 1 <= len(label) <= self.n and self.continues(label.frame)

    @override
    def is_end_of_lace(self, label: Dfs) -> bool:
        return label.next is None and (isinstance(label.frame.event, ERR_EVENTS) or len(label) == self.n + 1)

    @override
    def step_int(self, label: Dfs, expected_next_dir: Dir) -> Iterable[DfsFrame] | None:
        if expected_next_dir != Internal():
            return None
        f = self.step_int_frame(label)
        return None if f is None else [f.to_frozen()]

    @override
    def step_up(self, pair: Pair[DfsFrame], expected_next_dir: Dir) -> DfsFrame | None:
        sigma, tau = pair.child, pair.parent
        if len(tau) > self.n or expected_next_dir != Up():
            return None
        # Psi_Up: a node reached structurally pushes its state to the first unvisited child of the parent
        if sigma.frame.inst == PushState() and struct_tainted(sigma, len(sigma)):
            if pair.j != first_unvstd_child(tau.frame.child_state):
                return None
            f = self.struct_push_state_up(sigma, tau)
        else:
            f = self.step_ext(sigma, tau, expected_next_dir)
        return None if f is None else f.to_frozen()

    @override
    def step_down(self, pair: Pair[DfsFrame], expected_next_dir: Dir) -> DfsFrame | None:
        sigma, tau = pair.parent, pair.child
        if len(tau) > self.n or expected_next_dir != Down(pair.j):
            return None
        f = self.visit_down(sigma, tau, pair.j) if sigma.frame.inst == VisitNext() else None
        f = f or self.step_ext(sigma, tau, expected_next_dir)
        return None if f is None else f.to_frozen()

    # -----------------------------------------------------------------------
    # step^P
    # -----------------------------------------------------------------------

    def step_int_frame(self, sigma: Dfs) -> MutableDfsFrame | None:
        match sigma.frame.inst:
            case FindP(p):
                return self.find_here_int(sigma, p)
            case VisitNext():
                return self.visit_int(sigma)
            case Trans():
                return self.automaton_transition_int(sigma)
            case Accept():
                return self.step_accept_int(sigma)
            case PushState():
                return self.remote_push_state(sigma, sigma, Internal())
            case StateForward():
                return self.set_state_after_fwd_int(sigma)
            case _:
                return None

    def step_ext(self, sigma: Dfs, tau: Dfs, expected_next_dir: Dir) -> MutableDfsFrame | None:
        match sigma.frame.inst:
            case FindP(p):
                return self.fwd_taint_ext(sigma, tau, p, expected_next_dir)
            case PushState():
                return self.remote_push_state(sigma, tau, expected_next_dir)
            case StateForward():
                return self.fwd_state_ext(sigma, tau, expected_next_dir)
            case _:
                return None

    def error(self, f: DfsFrame, fbelow: DfsFrame, event: Event) -> MutableDfsFrame:
        """error^P: the new frame only records the error."""
        return default("node_state", "child_state", "inst", "relay")(f, fbelow, MutableDfsFrame(event=event))

    def _visit_error(self, node: Dfs, f: DfsFrame, fbelow: DfsFrame) -> MutableDfsFrame | None:
        """The node is reached by the visit: it must be active and never reached before."""
        if not active(sigma_of(node)):
            return self.error(f, fbelow, Dang())
        if fbelow.node_state in (Top(), Topp()):
            return self.error(f, fbelow, Loop())
        if fbelow.node_state == Q():
            return self.error(f, fbelow, Conv())
        return None

    # -----------------------------------------------------------------------
    # Visiting step
    # -----------------------------------------------------------------------

    def visit_int(self, sigma: Dfs) -> MutableDfsFrame | None:
        """step_visit^P, cases resolved on the current node: nil field, pointer field."""
        f, sigma_lab = sigma.frame, sigma_of(sigma)
        j = first_unvstd_child(f.child_state)
        if j is None:
            return None
        if child_is_nil(sigma_lab, j):
            return self.set_nil_state(f, j)
        match child_is_ptr(sigma_lab, j):
            case (p, i) if points_here(sigma_lab, i, p):
                return self.error(f, f, SelfLoop())
            case (p, i):
                return self.init_taint_fwd(f, p, i)
            case _:
                return None

    def visit_down(self, sigma: Dfs, tau: Dfs, j_child: int) -> MutableDfsFrame | None:
        """step_visit^P, structural field: the visit moves to the j-th child."""
        f = sigma.frame
        j = first_unvstd_child(f.child_state)
        if j is None or j != j_child or not child_is_struct(sigma_of(sigma), j):
            return None
        return self._visit_error(tau, f, tau.frame) or self.taint_struct_child(f, tau.frame)

    def taint_struct_child(self, f: DfsFrame, fbelow: DfsFrame) -> MutableDfsFrame:
        g = MutableDfsFrame(node_state=Top(), event=StructTaint(), inst=VisitNext())
        return default("relay", "child_state")(f, fbelow, g)

    def set_nil_state(self, f: DfsFrame, j: int) -> MutableDfsFrame:
        child_state = list(f.child_state)
        child_state[j] = Nil()
        g = MutableDfsFrame(child_state=child_state, inst=visit_or_trans(j, self.k))
        return default("node_state", "event", "relay")(f, f, g)

    def init_taint_fwd(self, f: DfsFrame, p: int, i: int) -> MutableDfsFrame:
        g = MutableDfsFrame(event=InitTFWD(i), inst=FindP(p), relay=Top())
        return default("node_state", "child_state")(f, f, g)

    # -----------------------------------------------------------------------
    # Taint forwarding
    # -----------------------------------------------------------------------

    @staticmethod
    def _tfwd_position(f: DfsFrame) -> int | None:
        match f.event:
            case InitTFWD(i) | TFWD(i):
                return i
            case _:
                return None

    def fwd_taint_ext(self, sigma: Dfs, tau: Dfs, p: int, expected_next_dir: Dir) -> MutableDfsFrame | None:
        """fwd_taint: rewind the Lab lace of σ to the last update of p, on the neighbour τ."""
        f, sigma_lab, tau_lab = sigma.frame, sigma_of(sigma), sigma_of(tau)
        i2 = self._tfwd_position(f)
        if i2 is None or sigma_lab[i2].isnil[p] or points_here(sigma_lab, i2, p):
            return None
        i_upd = last_upd(sigma_lab, i2, p)
        match prev_of(sigma_lab, i_upd):
            case (dir, i1) if dir == expected_next_dir and dir != Internal() and 1 <= i1 <= len(tau_lab):
                pass
            case _:
                return None
        match next_of(tau_lab, i1):
            case (dir_, c) if c == i_upd and are_opposite_directions(dir, dir_):
                pass
            case _:
                return None
        g = MutableDfsFrame(event=TFWD(i1), relay=f.relay)
        return default("node_state", "child_state", "inst")(f, tau.frame, g)

    def find_here_int(self, sigma: Dfs, p: int) -> MutableDfsFrame | None:
        """find_step, p points to the current node: taint it or report an error."""
        f, sigma_lab = sigma.frame, sigma_of(sigma)
        i = self._tfwd_position(f)
        if i is None or not points_here(sigma_lab, i, p):
            return None
        return self._visit_error(sigma, f, f) or self.set_taint_after_fwd(f)

    def set_taint_after_fwd(self, f: DfsFrame) -> MutableDfsFrame:
        g = MutableDfsFrame(node_state=f.relay, relay=Bot(), event=RemoteTaint(), inst=VisitNext())
        return default("child_state")(f, f, g)

    # -----------------------------------------------------------------------
    # Automaton transition and state propagation
    # -----------------------------------------------------------------------

    def automaton_transition_int(self, sigma: Dfs) -> MutableDfsFrame | None:
        f = sigma.frame
        if any(state == Bot() for state in f.child_state):
            return None
        match f.node_state:
            case Top():
                inst = PushState()
            case Topp():
                inst = Accept()
            case _:
                return None
        g = MutableDfsFrame(node_state=Q(), inst=inst)
        return default("child_state", "event", "relay")(f, f, g)

    def step_accept_int(self, sigma: Dfs) -> MutableDfsFrame | None:
        f = sigma.frame
        if f.node_state != Q():
            return None
        g = MutableDfsFrame(event=Acc(), inst=NoInst())
        return default("node_state", "child_state", "relay")(f, f, g)

    def struct_push_state_up(self, sigma: Dfs, tau: Dfs) -> MutableDfsFrame | None:
        """struct_push_state: the child σ gives its state to the parent τ."""
        f, fbelow = sigma.frame, tau.frame
        j = first_unvstd_child(fbelow.child_state)
        if j is None or f.node_state != Q():
            return None
        child_state = list(fbelow.child_state)
        child_state[j] = f.node_state
        g = MutableDfsFrame(child_state=child_state, inst=visit_or_trans(j, self.k))
        return default("node_state", "event", "relay")(f, fbelow, g)

    def remote_push_state(self, sigma: Dfs, tau: Dfs, expected_next_dir: Dir) -> MutableDfsFrame | None:
        """remote_push_state: the node reached through a taint forwarding sends its state back along it.

        The frame RemoteTaint follows internally the frame that found the node, so the first step back is
        internal when that frame is on the same node."""
        f = sigma.frame
        i1 = remote_tainted(sigma, len(sigma))
        if i1 is None or struct_tainted(sigma, len(sigma)) or f.node_state != Q():
            return None
        tau_full = tau if expected_next_dir != Internal() else sigma
        match prev_of(sigma, i1):
            case (dir, i2) if dir == expected_next_dir and 1 <= i2 <= len(tau_full):
                pass
            case _:
                return None
        match next_of(tau_full, i2):
            case (dir_, c) if c == i1 and (dir == Internal() == dir_ or are_opposite_directions(dir, dir_)):
                pass
            case _:
                return None
        g = MutableDfsFrame(relay=f.node_state, event=SFWD(i2), inst=StateForward())
        return default("node_state", "child_state")(f, tau_full.frame, g)

    def fwd_state_ext(self, sigma: Dfs, tau: Dfs, expected_next_dir: Dir) -> MutableDfsFrame | None:
        """fwd_state: follow the taint forwarding chain back, one frame at a time."""
        f = sigma.frame
        match f.event:
            case SFWD(i1) if isinstance(sigma[i1].event, TFWD):
                pass
            case _:
                return None
        match prev_of(sigma, i1):
            case (dir, i2) if dir == expected_next_dir and dir != Internal() and 1 <= i2 <= len(tau):
                pass
            case _:
                return None
        match next_of(tau, i2):
            case (dir_, c) if c == i1 and are_opposite_directions(dir, dir_):
                pass
            case _:
                return None
        g = MutableDfsFrame(event=SFWD(i2))
        return default("node_state", "child_state", "inst", "relay")(f, tau.frame, g)

    def set_state_after_fwd_int(self, sigma: Dfs) -> MutableDfsFrame | None:
        """The forwarded state reaches the node that started the forwarding: it becomes a child state."""
        f = sigma.frame
        match f.event:
            case SFWD(i) if isinstance(sigma[i].event, InitTFWD):
                pass
            case _:
                return None
        j = first_unvstd_child(f.child_state)
        if j is None:
            return None
        child_state = list(f.child_state)
        child_state[j] = f.relay
        g = MutableDfsFrame(child_state=child_state, inst=visit_or_trans(j, self.k), relay=Bot())
        return default("node_state", "event")(f, f, g)
