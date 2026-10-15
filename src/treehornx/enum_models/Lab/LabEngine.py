"""Symbolic engine for the Lab encoding of CAV25 (Appendix C).

Every predicate step_* of the paper is split by the direction of the lace step it produces:

* `_int`  the new frame extends the same label (σ.next^a = (−, a+1));
* `_down` the new frame is pushed on a child for sure (σ.next^a = (j, b));
* `_ext`  the new frame is pushed on the parent or on a child, depending on where the
          rewinding leads (σ.next^a = (dir, b)).

Each case receives `expected_next_dir`, the direction of the next field of the last frame σ^a,
and fails (returns None) when it does not match the direction the case requires.

Naming follows the paper: σ is the label holding the current last frame σ^a of the lace (a =
len(σ)), τ is the label receiving the new frame τ^b (b = len(τ) + 1). For `_int` steps τ = σ.
Data fields and data variables are not part of the frame, so instructions over data only
advance the pc and data conditions take both branches.
"""

from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable, override

from treehornx import ir
from treehornx.enum_models.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.core.SymbolicEngine import SymbolicEngine
from treehornx.enum_models.Lab.Event import ERR, OOM, FieldAssignP, Here, Rewind, RwdSpec
from treehornx.enum_models.Lab.Frame import Frame, MutableFrame
from treehornx.enum_models.Lab.helpers import (
    are_equal_after_rewind,
    cur_rewind_pos,
    default,
    is_pfield_implicit,
    is_pfield_nil,
    is_pfield_ptr,
    isnil_with,
    last_upd,
    last_visit,
    next_of,
    points_here,
    prev_of,
    stop_rewind,
    stop_rewind2,
    upd_since,
)


@dataclass
class LabEngine(SymbolicEngine[Frame]):
    function: ir.Function = field(kw_only=True)

    @cached_property
    def pointers(self) -> range:
        return range(len(self.function.pointer_vars))

    @cached_property
    def aux_children(self) -> range:
        return range(self.k, self.k + self.m)

    # -----------------------------------------------------------------------
    # SymbolicEngine interface
    # -----------------------------------------------------------------------

    def continues(self, f: Frame) -> bool:
        """frame_exit(f) = N"""
        return not isinstance(self.function[f.pc], ir.Exit) and not isinstance(f.event, (ERR, OOM))

    @override
    def is_continuos(self, label: Label[Frame]) -> bool:
        return label.next is None and 2 <= len(label) <= self.n and self.continues(label.frame)

    @override
    def is_end_of_lace(self, label: Label[Frame]) -> bool:
        return label.next is None and len(label) >= 2 and (len(label) == self.n + 1 or not self.continues(label.frame))

    @override
    def step_int(self, label: Label[Frame], expected_next_dir: Dir) -> Iterable[Frame] | None:
        frames = [f for f in self.step_int_frames(label, expected_next_dir) if f is not None]
        if not frames:
            return None
        for f in frames:
            # Psi_Internal: ∧_p ¬f.upd_p
            f.upd = [False for _ in self.pointers]
        return [f.to_frozen() for f in frames]

    @override
    def step_up(self, pair: Pair[Frame], expected_next_dir: Dir) -> Frame | None:
        if len(pair.parent) > self.n:
            return None
        f = self.step_ext(pair.child, pair.parent, expected_next_dir)
        if f is None:
            return None
        return self.step_up_with_upd(pair, f).to_frozen()

    @override
    def step_down(self, pair: Pair[Frame], expected_next_dir: Dir) -> Frame | None:
        if len(pair.child) > self.n:
            return None
        f = self.step_ext(pair.parent, pair.child, expected_next_dir)
        if f is None:
            return None
        return self.step_down_with_upd(pair, f).to_frozen()

    # -----------------------------------------------------------------------
    # Psi_Up / Psi_Down: update flags
    # -----------------------------------------------------------------------

    def step_up_with_upd(self, pair: Pair[Frame], f: MutableFrame) -> MutableFrame:
        """Psi_Up(τ, j, σ, f) without the step: τ is the j-th child (len a), σ the parent (len b - 1)."""
        tau, sigma, j = pair.child, pair.parent, pair.j
        a, b = len(tau), len(sigma) + 1
        assert f.active_child is not None and f.isnil is not None

        # f.active_child_j = τ^a.active, also the f.prev = (j, *) case of default_active_child
        f.active_child[j] = tau.frame.active

        match sigma.next:
            case (Down(j_), a_) if b > 2 and j_ == j:
                f.upd = [not f.isnil[p] and upd_since(tau, a_, a, p) for p in self.pointers]
            case _:
                f.upd = [False for _ in self.pointers]
        return f

    def step_down_with_upd(self, pair: Pair[Frame], f: MutableFrame) -> MutableFrame:
        """Psi_Down(σ, j, τ, f) without the step: σ is the parent (len a), τ the j-th child (len b - 1)."""
        sigma, tau = pair.parent, pair.child
        a, b = len(sigma), len(tau) + 1
        assert f.isnil is not None

        match tau.next:
            case (Up(), a_) if b > 2:
                f.upd = [not f.isnil[p] and upd_since(sigma, a_, a, p) for p in self.pointers]
            case _:
                f.upd = [False for _ in self.pointers]
        return f

    # -----------------------------------------------------------------------
    # step(σ, a; τ, b)
    # -----------------------------------------------------------------------

    def step_int_frames(self, sigma: Label[Frame], expected_next_dir: Dir) -> Iterable[MutableFrame | None]:
        d = expected_next_dir
        match self.function[sigma.frame.pc]:
            case ir.Goto():
                return [self.step_skip_int(sigma, d)]
            case ir.AssignData() | ir.AssignCond(_, ir.IsNil()):
                return [self.step_assgn_exp_int(sigma, d)]
            case ir.AssignCond(_, ir.PtrEq(p, q)):
                return [self.step_assgn_cond_int(sigma, p, q, d)]
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
            case ir.IfGoto(ir.DataCond(expr)):
                return self.step_local_branch_int(sigma, expr, d)
            case ir.Exit():
                return []
            case stmt:
                raise NotImplementedError(f"step not implemented for statement: {stmt}")

    def step_ext(self, sigma: Label[Frame], tau: Label[Frame], expected_next_dir: Dir) -> MutableFrame | None:
        d = expected_next_dir
        match self.function[sigma.frame.pc]:
            case ir.AssignCond(_, ir.PtrEq(p, q)):
                return self.step_assgn_cond_ext(sigma, tau, p, q, d)
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

    def step_skip_int(self, sigma: Label[Frame], expected_next_dir: Dir) -> MutableFrame | None:
        """skip / goto"""
        f1 = sigma.frame
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f1, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f1, f1, f2)

    def step_assgn_nil_int(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p := nil"""
        return self.step_assgn_nil(sigma.frame, p, expected_next_dir)

    def step_assgn_nil(self, f1: Frame, p: int, expected_next_dir: Dir) -> MutableFrame | None:
        if expected_next_dir != Internal():
            return None
        f2 = MutableFrame()
        f2.isnil = isnil_with(f1, p, True)
        f2 = self.advance_pc(f1, f2)
        return default("active", "event", "active_child")(f1, f1, f2)

    def step_assgn_exp_int(self, sigma: Label[Frame], expected_next_dir: Dir) -> MutableFrame | None:
        """d := exp (d is not tracked by the frame)"""
        f1 = sigma.frame
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f1, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f1, f1, f2)

    def step_new_int(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """new p, Case 1: out-of-memory error"""
        f = sigma.frame
        if not all(f.active_child[j] for j in self.aux_children) or expected_next_dir != Internal():
            return None
        f__ = MutableFrame(event=OOM())
        return default("active", "pc", "isnil", "active_child")(f, f, f__)

    def step_new_down(
        self, sigma: Label[Frame], tau: Label[Frame], p: int, expected_next_dir: Dir
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
        self, sigma: Label[Frame], expr: ir.DataExpr, expected_next_dir: Dir
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

    def find_or_fail_int(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """find_or_fail, failing case: p is nil"""
        if not sigma.frame.isnil[p]:
            return None
        return self.error(sigma.frame, expected_next_dir)

    def find_or_fail_ext(
        self, sigma: Label[Frame], tau: Label[Frame], p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """find_or_fail, finding case: start or keep rewinding"""
        return self.rewind(sigma, tau, p, expected_next_dir)

    def step_assgn_ptr_int(self, sigma: Label[Frame], p: int, q: int, expected_next_dir: Dir) -> MutableFrame | None:
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
        self, sigma: Label[Frame], tau: Label[Frame], p: int, q: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p := q, Case 2: q points elsewhere; start or keep rewinding"""
        return self.rewind(sigma, tau, q, expected_next_dir)

    def _store_field(
        self, sigma: Label[Frame], p: int, event: FieldAssignP, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p points to the current node: stores `event` in a new frame"""
        f, a = sigma.frame, len(sigma)
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame())
        f2.event = event
        return default("active", "isnil", "active_child")(f, f, f2)

    def step_assgn_to_field_int(
        self, sigma: Label[Frame], p: int, q: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> pfield := q"""
        f = sigma.frame
        if f.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        event = FieldAssignP(pfield, None) if f.isnil[q] else FieldAssignP(pfield, q)
        return self._store_field(sigma, p, event, expected_next_dir)

    def step_assgn_nil_to_field_int(
        self, sigma: Label[Frame], p: int, pfield: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> pfield := nil"""
        if sigma.frame.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        return self._store_field(sigma, p, FieldAssignP(pfield, None), expected_next_dir)

    def step_assgn_to_field_ext(
        self, sigma: Label[Frame], tau: Label[Frame], p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> pfield := q and p -> pfield := nil"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def _local_on_ptr(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p points to the current node: only advances the pc (val and d are not tracked)"""
        f, a = sigma.frame, len(sigma)
        if not stop_rewind(sigma, a, p) or expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame())
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    def step_assgn_to_data_int(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """p -> val := exp"""
        if sigma.frame.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        return self._local_on_ptr(sigma, p, expected_next_dir)

    def step_assgn_to_data_ext(
        self, sigma: Label[Frame], tau: Label[Frame], p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """p -> val := exp"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_assgn_to_var_int(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
        """d := p -> val"""
        if sigma.frame.isnil[p]:
            return self.find_or_fail_int(sigma, p, expected_next_dir)
        return self._local_on_ptr(sigma, p, expected_next_dir)

    def step_assgn_to_var_ext(
        self, sigma: Label[Frame], tau: Label[Frame], p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """d := p -> val"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_free_int(self, sigma: Label[Frame], p: int, expected_next_dir: Dir) -> MutableFrame | None:
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
        self, sigma: Label[Frame], tau: Label[Frame], p: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """free p"""
        return self.find_or_fail_ext(sigma, tau, p, expected_next_dir)

    def step_assgn_cond_int(self, sigma: Label[Frame], p: int, q: int, expected_next_dir: Dir) -> MutableFrame | None:
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
        self, sigma: Label[Frame], tau: Label[Frame], p: int, q: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """dbool := (p = q), Case 2: start or keep rewinding"""
        return self.rewind2(sigma, tau, p, q, expected_next_dir)

    def step_assgn_from_field_int(
        self, sigma: Label[Frame], p: int, q: int, pfield: int, expected_next_dir: Dir
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
                if is_pfield_nil(sigma, a, pfield) or (
                    is_pfield_implicit(sigma, a, pfield) and not f.active_child[pfield]
                ):
                    return self.step_assgn_nil(f, p, expected_next_dir)
                for r in self.pointers:
                    for i in range(2, a + 1):
                        if is_pfield_ptr(sigma, a, pfield, r, i) and points_here(sigma, i, r):
                            return self.set_ptr_here(f, p, expected_next_dir)
                return None
            case _:
                return None

    def step_assgn_from_field_down(
        self, sigma: Label[Frame], tau: Label[Frame], p: int, q: int, pfield: int, expected_next_dir: Dir
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
        self, sigma: Label[Frame], tau: Label[Frame], p: int, q: int, pfield: int, expected_next_dir: Dir
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
                for r in self.pointers:
                    for i in range(2, a + 1):
                        if is_pfield_ptr(sigma, a, pfield, r, i) and not points_here(sigma, i, r):
                            return self.rewind_special(sigma, tau, r, i, expected_next_dir)
                return None

    # -----------------------------------------------------------------------
    # Boolean conditions and control-flow instructions (C.6)
    # -----------------------------------------------------------------------

    def step_cmp_ptr_int(
        self, sigma: Label[Frame], p: int, q: int, neg: bool, expected_next_dir: Dir
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
        self, sigma: Label[Frame], tau: Label[Frame], p: int, q: int, expected_next_dir: Dir
    ) -> MutableFrame | None:
        """if p = q / if p != q, Case 2: start or keep rewinding"""
        return self.rewind2(sigma, tau, p, q, expected_next_dir)

    def step_cmp_nil_int(self, sigma: Label[Frame], p: int, neg: bool, expected_next_dir: Dir) -> MutableFrame | None:
        """if p = nil (neg = False) / if p != nil (neg = True)"""
        f = sigma.frame
        if expected_next_dir != Internal():
            return None
        f2 = self.advance_pc(f, MutableFrame(), neg != f.isnil[p])
        return default("active", "isnil", "event", "active_child")(f, f, f2)

    # -----------------------------------------------------------------------
    # Rewinding the lace (C.7)
    # -----------------------------------------------------------------------

    def rewind_origin(
        self, sigma: Label[Frame], tau: Label[Frame], a__: int, expected_next_dir: Dir
    ) -> int | None:
        """Part shared by rewind, rewind2 and rewind_special, returns b' such that

        σ^a.next = (dir, b) ∧ σ^{a''}.prev = (dir, b') ∧ τ^{b'}.next = (dir', a'') ∧
        b = last_visit(τ, dir', a) + 1

        The paper bounds last_visit by a' instead of a, which rejects valid rewinds whenever
        τ moved to σ after position a' (e.g. a rewind restarted from a frame rwd_{a'}).
        """
        a = len(sigma)
        match prev_of(sigma, a__):
            case (dir, b_) if dir == expected_next_dir and dir != Internal() and 1 <= b_ <= len(tau):
                pass
            case _:
                return None
        match next_of(tau, b_):
            case (dir_, c) if c == a__ and last_visit(tau, dir_, a) == len(tau):
                return b_
            case _:
                return None

    def rewind(self, sigma: Label[Frame], tau: Label[Frame], q: int, expected_next_dir: Dir) -> MutableFrame | None:
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
        self, sigma: Label[Frame], tau: Label[Frame], q1: int, q2: int, expected_next_dir: Dir
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
        self, sigma: Label[Frame], tau: Label[Frame], r: int, a_: int, expected_next_dir: Dir
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
