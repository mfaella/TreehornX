"""Symbolic engine for the Lab encoding of CAV25 (Appendix C).

Every predicate step_* of the paper is split by the direction of the lace step it produces:

* `_int`  the new frame extends the same label (its prev is (−, a));
* `_down` the new frame is pushed on a child for sure (its prev is (Up, a));
* `_ext`  the new frame is pushed on the parent or on a child, depending on where the
          rewinding leads (its prev is (Down(j), a) or (Up, a)).

Each case receives `expected_next_dir`, the direction in which the lace leaves the last frame
σ^a, and fails (returns None) when it does not match the direction the case requires. The prev
link of the new frame is set by step_int/step_up/step_down, once the receiver is known.

Naming follows the paper: σ is the label holding the current last frame σ^a of the lace (a =
len(σ)), τ is the label receiving the new frame τ^b (b = len(τ) + 1). For `_int` steps τ = σ.
Data fields and data variables are not part of the frame, so instructions over data only
advance the pc and data conditions take both branches.
"""

from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Iterable, override

from treehornx import ir
from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Lab.ExitCode import ExitCode
from treehornx.enum_models.Lab.initial import backbone_labels, initial_pairs, start_labels
from treehornx.enum_models.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.core.SymbolicEngine import SymbolicEngine
from treehornx.enum_models.Lab.Event import ERR, OOM, FieldAssignP, Here, Rewind, RwdSpec
from treehornx.enum_models.Lab.Frame import Frame, MutableFrame
from treehornx.enum_models.Lab.helpers import (
    are_equal_after_rewind,
    cur_rewind_pos,
    default,
    field_is_nil,
    is_pfield_implicit,
    get_pfield_ptr,
    isnil_with,
    last_upd,
    points_here,
    stop_rewind,
    stop_rewind2,
    upd_since,
)


@dataclass(init=False)
class LabEngine(SymbolicEngine[Lab]):
    n: int
    function: ir.Function

    def __init__(self, k: int, m: int, n: int, function: ir.Function):
        starts = set(start_labels(function, m))
        backbones = set(backbone_labels(function, m))
        init_pairs = set(initial_pairs(function, m, starts, backbones))
        super().__init__(k=k, m=m, initial_pairs=init_pairs, start_states=starts)
        self.n = n
        self.function = function

    @cached_property
    def pointers(self) -> range:
        return range(len(self.function.pointer_vars))

    @cached_property
    def aux_children(self) -> range:
        return range(self.k, self.k + self.m)

    # -----------------------------------------------------------------------
    # SymbolicEngine interface
    # -----------------------------------------------------------------------

    def is_continuos(self, label: Lab) -> bool:
        # a label of length 1 holds only the frame before the lace reaches the node: it cannot step
        return len(label) >= 2 and self.label_exit(label) == ExitCode.N

    def label_exit(self, label: Lab) -> ExitCode:
        match label.frame.event:
            case ERR():
                return ExitCode.E
            case OOM():
                return ExitCode.M
            case _ if isinstance(self.function[label.frame.pc], ir.Exit):
                return ExitCode.C
            case _ if len(label) > self.n:
                return ExitCode.O
            case _:
                return ExitCode.N

    def is_end_of_lace(self, label: Lab) -> bool:
        return self.label_exit(label) != ExitCode.N

    def parent_leadership(self, pair: Pair[Lab]) -> bool:
        if len(pair.child) == 1 or len(pair.parent) == 1:
            return True
        for f in reversed(pair.parent[2:]):
            if f.prev == (Down(pair.j), len(pair.child)):
                return True

        return False

    def child_leadership(self, pair: Pair[Lab]) -> bool:
        return not self.parent_leadership(pair)

    @override
    def consistent(self, pair: Pair[Lab]) -> bool:
        """Every pair is consistent by construction.

        Initial pairs are filtered by consistent_first_frames, step_up/step_down extend a pair
        with matching prev links, and find_new_pairs only propagates the parent's internal steps
        and steps from children j' != j, and the child's non-Up steps. Since a label either steps
        internally or sends the lace out (never both), the parent cannot advance while the lace
        is in the j-th child, so the prev links of the two labels never contradict each other."""
        return True

    @override
    def step_int(self, label: Lab) -> Iterable[Lab] | None:
        if not self.is_continuos(label):
            return None
        frames = [f for f in self.step_int_frames(label, Internal()) if f is not None]
        if not frames:
            return None
        for f in frames:
            # Psi_Internal: ∧_p ¬f.upd_p
            f.upd = [False for _ in self.pointers]
            f.prev = (Internal(), len(label))
        return (Lab(f.to_frozen(), label) for f in frames)

    @override
    def step_up(self, pair: Pair[Lab]) -> Pair[Lab] | None:
        if not self.is_continuos(pair.child):
            return None
        if not self.child_leadership(pair):
            return None
        f = self.step_up_with_upd(pair)
        if f is None:
            return None
        f.prev = (Down(pair.j), len(pair.child))
        new_parent = Lab(f.to_frozen(), pair.parent)
        new_pair = replace(pair, parent=new_parent)
        return new_pair

    @override
    def step_down(self, pair: Pair[Lab]) -> Pair[Lab] | None:
        if not self.is_continuos(pair.parent):
            return None
        if not self.parent_leadership(pair):
            return None
        f = self.step_down_with_upd(pair)
        if f is None:
            return None
        f.prev = (Up(), len(pair.parent))
        new_child = Lab(f.to_frozen(), pair.child)
        new_pair = replace(pair, child=new_child)
        return new_pair

    # -----------------------------------------------------------------------
    # Psi_Up / Psi_Down: update flags
    # -----------------------------------------------------------------------

    def step_up_with_upd(self, pair: Pair[Lab]) -> MutableFrame | None:
        """Psi_Up(τ, j, σ, f) without the step: τ is the j-th child (len a), σ the parent (len b - 1)."""
        tau, sigma, j = pair.child, pair.parent, pair.j
        a, b = len(tau), len(sigma) + 1
        frame = self.step_ext(tau, sigma, expected_next_dir=Up())
        if frame is None:
            return None
        assert frame.active_child is not None and frame.isnil is not None

        # f.active_child_j = τ^a.active, also the f.prev = (j, *) case of default_active_child
        frame.active_child[j] = tau.frame.active

        if b <= 2:
            frame.upd = [False for _ in self.pointers]
        else:
            a_ = next(i for i, f in enumerate(tau[2:], start = 2) if f.prev == (Up(), b - 1))
            frame.upd = [not frame.isnil[p] and upd_since(tau, a_, a, p) for p in self.pointers]
        return frame

    def step_down_with_upd(self, pair: Pair[Lab]) -> MutableFrame | None:
        """Psi_Down(σ, j, τ, f) without the step: σ is the parent (len a), τ the j-th child (len b - 1)."""
        sigma, tau = pair.parent, pair.child
        a, b = len(sigma), len(tau) + 1
        frame = self.step_ext(sigma, tau, expected_next_dir=Down(pair.j))
        if frame is None:
            return None
        assert frame.isnil is not None

        if b <= 2:
            frame.upd = [False for _ in self.pointers]
        else:
            a_ = next(i for i, f in enumerate(sigma[2:], start = 2) if f.prev == (Down(pair.j), b - 1))
            frame.upd = [not frame.isnil[p] and upd_since(sigma, a_, a, p) for p in self.pointers]
        return frame

    # -----------------------------------------------------------------------
    # step(σ, a; τ, b)
    # -----------------------------------------------------------------------

    def step_int_frames(self, sigma: Lab, expected_next_dir: Dir) -> Iterable[MutableFrame | None]:
        d = expected_next_dir
        match self.function[sigma.frame.pc]:
            case ir.Goto():
                return [self.step_skip_int(sigma, d)]
            case ir.AssignData() | ir.AssignCond(_, ir.IsNil()):
                return [self.step_assgn_exp_int(sigma, d)]
            case ir.AssignCond(_, ir.PtrEq(p, q)):
                return [self.step_assgn_cond_int(sigma, p, q, d)]
            case ir.AssignCond(_, ir.FieldIsNil(p, _, _)):
                return [self.step_assgn_cond_field_nil_int(sigma, p, d)]
            case ir.AssignNil(p):
                return [self.step_assgn_nil_int(sigma, p, d)]
            case ir.AssignPtr(p, q):
                return [self.step_assgn_ptr_int(sigma, p, q, d)]
            case ir.LoadPtrField(p, q, pfield):
                return [self.step_assgn_from_field_int(sigma, p, q, pfield, d)]
            case ir.StoreNilField(p, pfield):
                return [self.step_assgn_nil_to_field_int(sigma, p, pfield, d)]
            case ir.StorePtrField(p, pfield, q):
                return [self.step_assgn_to_field_int(sigma, p, q, pfield, d)]
            case ir.StoreDataField(p, _, _):
                return [self.step_assgn_to_data_int(sigma, p, d)]
            case ir.LoadDataField(_, p, _):
                return [self.step_assgn_to_var_int(sigma, p, d)]
            case ir.New(p):
                return [self.step_new_int(sigma, p, d)]
            case ir.Free(p):
                return [self.step_free_int(sigma, p, d)]
            case ir.IfGoto(ir.PtrEq(p, q, neg)):
                return [self.step_cmp_ptr_int(sigma, p, q, neg, d)]
            case ir.IfGoto(ir.IsNil(p, neg)):
                return [self.step_cmp_nil_int(sigma, p, neg, d)]
            case ir.IfGoto(ir.FieldIsNil(p, pfield, neg)):
                return [self.step_cmp_field_nil_int(sigma, p, pfield, neg, d)]
            case ir.IfGoto(ir.DataCond(expr)):
                return self.step_local_branch_int(sigma, expr, d)
            case ir.Exit():
                return []
            case stmt:
                raise NotImplementedError(f"step not implemented for statement: {stmt}")

    def step_ext(self, sigma: Lab, tau: Lab, expected_next_dir: Dir) -> MutableFrame | None:
        d = expected_next_dir
        match self.function[sigma.frame.pc]:
            case ir.AssignCond(_, ir.PtrEq(p, q)):
                return self.step_assgn_cond_ext(sigma, tau, p, q, d)
            case ir.AssignCond(_, ir.FieldIsNil(p, _, _)):
                return self.step_assgn_cond_field_nil_ext(sigma, tau, p, d)
            case ir.AssignPtr(p, q):
                return self.step_assgn_ptr_ext(sigma, tau, p, q, d)
            case ir.LoadPtrField(p, q, pfield):
                return self.step_assgn_from_field_ext(sigma, tau, p, q, pfield, d) or self.step_assgn_from_field_down(
                    sigma, tau, p, q, pfield, d
                )
            case ir.StoreNilField(p, _) | ir.StorePtrField(p, _, _):
                return self.step_assgn_to_field_ext(sigma, tau, p, d)
            case ir.StoreDataField(p, _, _):
                return self.step_assgn_to_data_ext(sigma, tau, p, d)
            case ir.LoadDataField(_, p, _):
                return self.step_assgn_to_var_ext(sigma, tau, p, d)
            case ir.New(p):
                return self.step_new_down(sigma, tau, p, d)
            case ir.Free(p):
                return self.step_free_ext(sigma, tau, p, d)
            case ir.IfGoto(ir.PtrEq(p, q, _)):
                return self.step_cmp_ptr_ext(sigma, tau, p, q, d)
            case ir.IfGoto(ir.FieldIsNil(p, _, _)):
                return self.step_cmp_field_nil_ext(sigma, tau, p, d)
            case _:
                return None

    def advance_pc(self, f1: Frame, f2: MutableFrame, cond: bool | None = None) -> MutableFrame:
        """f2.pc = succ(f1.pc) or, for branching statements, f2.pc = succ(f1.pc, cond)"""
        succ = self.function.next_pc(f1.pc)
        if cond is None:
            assert isinstance(succ, int)
            f2.pc = succ
        else:
            assert isinstance(succ, tuple)
            f2.pc = succ[0] if cond else succ[1]
        return f2

    # -----------------------------------------------------------------------
    # Internal instructions
    # -----------------------------------------------------------------------

    def step_skip_int(self, sigma: Lab, expected_next_dir: Dir) -> MutableFrame | None:
        """skip / goto"""
        f1 = sigma.frame
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f1, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f1, f1, f2)

    def step_assgn_nil_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p := nil"""
        return self.step_assgn_nil(sigma.frame, p, expected_next_dir)

    def step_assgn_nil(self, f1: Frame, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        if expected_next_dir != Internal():
            return None
        f2 = MutableFrame()
        f2.isnil = isnil_with(f1, p, True)
        f2 = self.advance_pc(f1, f2)
        return default("active", "event", "active_child")(f1, f1, f2)

    def step_assgn_exp_int(self, sigma: Lab, expected_next_dir: Dir) -> MutableFrame | None:
        """d := exp (d is not tracked by the frame)"""
        f1 = sigma.frame
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f1, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f1, f1, f2)

    def step_new_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """new p, Case 1: out-of-memory error"""
        f = sigma.frame
        if not all(f.active_child[j] for j in self.aux_children) or expected_next_dir != Internal():
            return None
        f__ = MutableFrame(event=OOM())
        return default("active", "pc", "isnil", "active_child")(f, f, f__)

    def step_new_down(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """new p, Case 2: normal case"""
        f, f_ = sigma.frame, tau.frame
        j = next((j for j in self.aux_children if not f.active_child[j]), None)
        if j is None or expected_next_dir != Down(j):
            return None
        f__ = MutableFrame()
        f__.isnil = isnil_with(f, p, False)
        f__.event = Here(p)
        f__.active = True
        f__ = self.advance_pc(f, f__)
        return default("active_child")(f, f_, f__)

    def step_local_branch_int(
        self, sigma: Lab, expr: ir.DataExpr, expected_next_dir: Dir
    ) -> list[MutableFrame | None]:
        """if r(exp_1, ..., exp_l): data are not tracked, so a non-constant condition takes both branches"""
        f1 = sigma.frame
        if expected_next_dir != Internal():
            return []
        conds = [bool(expr.value)] if isinstance(expr, ir.Const) else [True, False]
        return [
            default("active", "isnil", "event", "active_child")(f1, f1, self.advance_pc(f1, MutableFrame(), cond))
            for cond in conds
        ]

    # -----------------------------------------------------------------------
    # Walking instructions
    # -----------------------------------------------------------------------

    def set_ptr_here(self, f1: Frame, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f1, MutableFrame())
        f2.event = Here(p)
        f2.isnil = isnil_with(f1, p, False)
        return default("active", "active_child")(f1, f1, f2)

    def error(self, f1: Frame, expected_next_dir: Dir) -> MutableFrame | None:
        if expected_next_dir != Internal():
            return None
        f2 = MutableFrame(event=ERR())
        return default("active", "isnil", "pc", "active_child")(f1, f1, f2)

    def find_or_fail_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """find_or_fail, failing case: p is nil"""
        if not sigma.frame.isnil[p]:
            return None
        return self.error(sigma.frame, expected_next_dir)

    def find_or_fail_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """find_or_fail, finding case: start or keep rewinding"""
        return self.rewind(sigma, tau, p, expected_next_dir)

    def step_assgn_ptr_int(self, sigma: Lab, p: int, q: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p := q"""
        f, a = sigma.frame, len(sigma)
        # Case 1: q is nil; use the encoding for p := nil
        if f.isnil[q]:
            return self.step_assgn_nil(f, p, expected_next_dir)
        # Case 3: q points to the current node
        if stop_rewind(sigma, a, q):
            return self.set_ptr_here(f, p, expected_next_dir)
        return None

    def step_assgn_ptr_ext(
        self, sigma: Lab, tau: Lab, p: int, q: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p := q, Case 2: q points elsewhere; start or keep rewinding"""
        return self.rewind(sigma, tau, q, expected_next_dir)

    def _store_field(
        self, sigma: Lab, p: int, event: FieldAssignP, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p points to the current node: stores `event` in a new frame"""
        f, a = sigma.frame, len(sigma)
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame())
        f2.event = event
        return default("active", "isnil", "active_child")(f, f, f2)

    def step_assgn_to_field_int(
        self, sigma: Lab, p: int, q: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> pfield := q"""
        f = sigma.frame
        if f.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        event = FieldAssignP(pfield, None) if f.isnil[q] else FieldAssignP(pfield, q)
        return self._store_field(sigma, p, event, expected_next_dir)

    def step_assgn_nil_to_field_int(
        self, sigma: Lab, p: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> pfield := nil"""
        if sigma.frame.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        return self._store_field(sigma, p, FieldAssignP(pfield, None), expected_next_dir)

    def step_assgn_to_field_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> pfield := q and p -> pfield := nil"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def _local_on_ptr(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p points to the current node: only advances the pc (val and d are not tracked)"""
        f, a = sigma.frame, len(sigma)
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_assgn_to_data_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p -> val := exp"""
        if sigma.frame.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        return self._local_on_ptr(sigma, p, expected_next_dir)

    def step_assgn_to_data_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> val := exp"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_assgn_to_var_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """d := p -> val"""
        if sigma.frame.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        return self._local_on_ptr(sigma, p, expected_next_dir)

    def step_assgn_to_var_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """d := p -> val"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_free_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """free p"""
        f, a = sigma.frame, len(sigma)
        if f.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        # p points to the current node
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame())
        f2.active = False
        f2.isnil = [True if points_here(sigma, a, q) else f.isnil[q] for q in self.pointers]
        return default("event", "active_child")(f, f, f2)

    def step_free_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """free p"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_assgn_cond_int(self, sigma: Lab, p: int, q: int, expected_next_dir: Dir) -> MutableFrame | None:
        """dbool := (p = q) (dbool is not tracked by the frame)"""
        f, a = sigma.frame, len(sigma)
        if expected_next_dir != Internal():
            return None
        # Case 1: at least one pointer is nil, Case 3: stop rewinding
        if not (f.isnil[p] or f.isnil[q]) and not stop_rewind2(sigma, a, p, q):
            return None
        f2 = self.advance_pc(f, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_assgn_cond_ext(
        self, sigma: Lab, tau: Lab, p: int, q: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """dbool := (p = q), Case 2: start or keep rewinding"""
        return self.rewind2(sigma, tau, p, q, expected_next_dir)

    def step_assgn_cond_field_nil_int(self, sigma: Lab, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """dbool := (p -> pfield = nil) (dbool is not tracked by the frame)"""
        f, a = sigma.frame, len(sigma)
        # Case 1: p is nil; null pointer dereference
        if f.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        # Case 3: p points to the current node
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_assgn_cond_field_nil_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """dbool := (p -> pfield = nil), Case 2: p points elsewhere; start or keep rewinding"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_assgn_from_field_int(
        self, sigma: Lab, p: int, q: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p := q -> pfield"""
        f, a = sigma.frame, len(sigma)
        # Case 1: q is nil; null pointer dereference
        if f.isnil[q]:
            return self.error(f, expected_next_dir)
        match f.event:
            # Case 3b: end of phase II; r points to the current node
            case RwdSpec(i, r):
                if points_here(sigma, i, r):
                    return self.set_ptr_here(f, p, expected_next_dir)
                return None
            # Case 3a: end of phase I; q points to the current node
            case _ if stop_rewind(sigma, a, q):
                if field_is_nil(sigma, a, pfield):
                    return self.step_assgn_nil(f, p, expected_next_dir)
                ptr = get_pfield_ptr(sigma, a, pfield)
                if ptr is not None and points_here(sigma, ptr[1], ptr[0]):
                    return self.set_ptr_here(f, p, expected_next_dir)
                return None
            case _:
                return None

    def step_assgn_from_field_down(
        self, sigma: Lab, tau: Lab, p: int, q: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p := q -> pfield, Case 3a: pfield is implicit and points to an active child"""
        f, a = sigma.frame, len(sigma)
        if (
            f.isnil[q]
            or isinstance(f.event, RwdSpec)
            or not stop_rewind(sigma, a, q)
            or not (is_pfield_implicit(sigma, a, pfield) and f.active_child[pfield])
            or expected_next_dir != Down(pfield)
        ):
            return None
        f2 = self.advance_pc(f, MutableFrame())
        f2.event = Here(p)
        # the paper defaults isnil here, but p now points to the child
        f2.isnil = isnil_with(f, p, False)
        return default("active", "active_child")(f, tau.frame, f2)

    def step_assgn_from_field_ext(
        self, sigma: Lab, tau: Lab, p: int, q: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p := q -> pfield"""
        f, a = sigma.frame, len(sigma)
        if f.isnil[q]:
            return None
        match f.event:
            # Case 2b: phase II; r points elsewhere; start or keep rewinding
            case RwdSpec(i, r):
                return self.rewind_special(sigma, tau, r, i, expected_next_dir)
            # Case 2a: phase I; q points elsewhere; start or keep rewinding
            case _ if not stop_rewind(sigma, a, q):
                return self.rewind(sigma, tau, q, expected_next_dir)
            # Case 3a: end of phase I; pfield is equal to r, which points elsewhere
            case _:
                ptr = get_pfield_ptr(sigma, a, pfield)
                if ptr is not None and not points_here(sigma, ptr[1], ptr[0]):
                    r, i = ptr
                    return self.rewind_special(sigma, tau, r, i, expected_next_dir)
                return None

    # -----------------------------------------------------------------------
    # Boolean conditions and control-flow instructions (C.6)
    # -----------------------------------------------------------------------

    def step_cmp_ptr_int(
        self, sigma: Lab, p: int, q: int, neg: bool, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """if p = q (neg = False) / if p != q (neg = True)"""
        f, a = sigma.frame, len(sigma)
        if expected_next_dir != Internal():
            return None
        # Case 1: at least one pointer is nil
        if f.isnil[p] or f.isnil[q]:
            cond = neg != (f.isnil[p] == f.isnil[q])
        # Case 3: stop rewinding
        elif stop_rewind2(sigma, a, p, q):
            cond = neg != are_equal_after_rewind(sigma, a, p, q)
        else:
            return None
        f2 = self.advance_pc(f, MutableFrame(), cond)
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_cmp_ptr_ext(
        self, sigma: Lab, tau: Lab, p: int, q: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """if p = q / if p != q, Case 2: start or keep rewinding"""
        return self.rewind2(sigma, tau, p, q, expected_next_dir)

    def step_cmp_nil_int(self, sigma: Lab, p: int, neg: bool, expected_next_dir: Dir) -> MutableFrame | None:
        """if p = nil (neg = False) / if p != nil (neg = True)"""
        f = sigma.frame
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame(), neg != f.isnil[p])
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_cmp_field_nil_int(
        self, sigma: Lab, p: int, pfield: int, neg: bool, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """if p -> pfield = nil (neg = False) / if p -> pfield != nil (neg = True)

        The field is read at the node p points to, without visiting the node it points to."""
        f, a = sigma.frame, len(sigma)
        # Case 1: p is nil; null pointer dereference
        if f.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        # Case 3: p points to the current node; branch on the value of the field
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame(), neg != field_is_nil(sigma, a, pfield))
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_cmp_field_nil_ext(
        self, sigma: Lab, tau: Lab, p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """if p -> pfield = nil / if p -> pfield != nil, Case 2: p points elsewhere; start or keep rewinding"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    # -----------------------------------------------------------------------
    # Rewinding the lace (C.7)
    # -----------------------------------------------------------------------

    def rewind_origin(
        self, sigma: Lab, tau: Lab, a__: int, expected_next_dir: Dir
    ) -> int | None:
        """Part shared by rewind, rewind2 and rewind_special, returns b' such that

        σ^{a''}.prev = (dir, b') ∧ dir = expected_next_dir ≠ − ∧ b' ∈ [1, len(τ)]

        The paper also requires τ^{b'}.next = (dir', a'') ∧ b = last_visit(τ, dir', a) + 1, i.e.
        that the new frame follows the last frame of τ that moved the lace to σ. That is guaranteed
        by the leadership checks of step_up/step_down: σ leads, so the last frame of τ is the one
        that moved the lace to σ.
        """
        match sigma[a__].prev:
            case (dir, b_) if dir == expected_next_dir and dir != Internal() and 1 <= b_ <= len(tau):
                return b_
            case _:
                return None

    def rewind(self, sigma: Lab, tau: Lab, q: int, expected_next_dir: Dir) -> MutableFrame | None:
        f, a = sigma.frame, len(sigma)
        if f.isnil[q]:
            return None
        a_ = cur_rewind_pos(sigma, a)
        if points_here(sigma, a_, q):
            return None
        a__ = last_upd(sigma, a_, q)
        b_ = self.rewind_origin(sigma, tau, a__, expected_next_dir)
        if b_ is None:
            return None
        f2 = MutableFrame(event=Rewind(b_))
        return default("active", "pc", "isnil", "active_child")(f, tau.frame, f2)

    def rewind2(
        self, sigma: Lab, tau: Lab, q1: int, q2: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        f, a = sigma.frame, len(sigma)
        if f.isnil[q1] or f.isnil[q2]:
            return None
        a_ = cur_rewind_pos(sigma, a)
        if points_here(sigma, a_, q1) or points_here(sigma, a_, q2):
            return None
        a__ = max(last_upd(sigma, a_, q1), last_upd(sigma, a_, q2))
        b_ = self.rewind_origin(sigma, tau, a__, expected_next_dir)
        if b_ is None:
            return None
        f2 = MutableFrame(event=Rewind(b_))
        return default("active", "pc", "isnil", "active_child")(f, tau.frame, f2)

    def rewind_special(
        self, sigma: Lab, tau: Lab, r: int, a_: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """Rewinding of the second phase of p := q -> pfield, looking for the value r had at (σ, a').

        The paper also requires ¬σ^a.isnil_r, which is omitted: the current value of r is
        irrelevant, r may have been set to nil after ⟨pfield := r⟩ was recorded."""
        f = sigma.frame
        if points_here(sigma, a_, r):
            return None
        a__ = last_upd(sigma, a_, r)
        b_ = self.rewind_origin(sigma, tau, a__, expected_next_dir)
        if b_ is None:
            return None
        f2 = MutableFrame(event=RwdSpec(b_, r))
        return default("active", "pc", "isnil", "active_child")(f, tau.frame, f2)

    @override
    def is_end_of_computation(self, state: Lab) -> bool:
        return self.is_end_of_lace(state)
