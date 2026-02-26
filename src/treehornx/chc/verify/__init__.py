from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any, List

import treehornx.ir.expressions as ire
from treehornx.chc.core import Frame, Label, Pair
from treehornx.chc.core.dir import Down, Internal, Up, are_opposite_directions
from treehornx.chc.core.event import ERR, LOF, NOP, OOM, Exit, FieldAssignP, Here, Rewind, Rewind2
from treehornx.chc.ppexp import ppexp
from treehornx.ir.expressions import EnumConst, Expr, Field, Var, sort_of
from treehornx.ir.function import Function
from treehornx.ir.instructions import (
    FieldAssignExpr,
    FieldAssignNil,
    FieldAssignPtr,
    Free,
    Goto,
    IfGoto,
    New,
    PtrAssignField,
    PtrAssignNil,
    PtrAssignPtr,
    Return,
    Skip,
    VarAssignExpr,
)
from treehornx.ir.sorts import BOOL

from ..core import *

# helpers


def xor(left: bool, right: bool) -> bool:
    return (left or right) and (not left and not right)


def implies(left: bool, right: bool) -> bool:
    return right if left else True


@dataclass
class CHCVerifier:
    function: Function | None = None
    root: Var | None = None
    m: int = 0
    n: int = 0
    k: int = 0

    def __post_init__(self) -> None:
        if self.root is not None:
            assert self.root.sort.is_ptr()
            root_sort = self.root.sort.pointee
            assert root_sort.is_struct()  # type: ignore[truthy-bool]
            computed_k = sum(1 for f in root_sort.fields.values() if f.sort.is_ptr())  # type: ignore[attr-defined]
            if self.k == 0:
                self.k = computed_k
            else:
                assert self.k == computed_k
        self._current_child_key: str | int | None = None

    def _require_program(self) -> None:
        if self.function is None:
            raise ValueError("CHCVerifier requires a function to interpret instructions")
        if self.root is None:
            raise ValueError("CHCVerifier requires a root pointer variable")

    @cached_property
    def pointers(self) -> tuple[str, ...]:
        self._require_program()
        assert self.function is not None
        return tuple(v.name for v in self.function.vars if v.sort.is_ptr())

    @cached_property
    def data_vars(self) -> tuple[str, ...]:
        self._require_program()
        assert self.function is not None
        return tuple(v.name for v in self.function.vars if v.sort.is_enum())

    @cached_property
    def pointer_fields(self) -> tuple[str, ...]:
        self._require_program()
        assert self.root is not None
        root_sort = self.root.sort.pointee
        assert root_sort.is_struct()  # type: ignore[truthy-bool]
        return tuple(name for name, f in root_sort.fields.items() if f.sort.is_ptr())  # type: ignore[attr-defined]

    @cached_property
    def enum_fields(self) -> tuple[str, ...]:
        self._require_program()
        assert self.root is not None
        root_sort = self.root.sort.pointee
        assert root_sort.is_struct()  # type: ignore[truthy-bool]
        return tuple(name for name, f in root_sort.fields.items() if f.sort.is_enum())  # type: ignore[attr-defined]

    @cached_property
    def indexed_children_keys(self) -> tuple[int, ...]:
        return tuple(range(self.k, self.k + self.m))

    @cached_property
    def children_keys(self) -> tuple[str | int, ...]:
        return (*self.pointer_fields, *self.indexed_children_keys)

    def _frames(self, sigma: Label) -> list[Frame]:
        return sorted(sigma.iter(), key=lambda f: f.index)

    def _frame_at(self, sigma: Label, index: int) -> Frame | None:
        for f in sigma.backward_iter():
            if f.index == index:
                return f
        return None

    def _label_prefix(self, sigma: Label, last_index: int) -> Label:
        frames = [f for f in self._frames(sigma) if f.index <= last_index]
        return Label.make(*frames)

    def _len_label(self, sigma: Label, a: int) -> bool:
        return len(sigma) == a + 1
        return True

    def _default_fields(self, f_prev: Frame, f_below: Frame, f: Frame, fields: set[str]) -> bool:
        if "active" in fields and f.active != f_below.active:
            return False
        if "enum_fields" in fields:
            for name in self.enum_fields:
                if f.enum_fields.get(name) != f_below.enum_fields.get(name):
                    return False
        if "enum_values" in fields:
            for name in self.data_vars:
                if f.enum_values.get(name) != f_prev.enum_values.get(name):
                    return False
        if "isnil" in fields:
            for p in self.pointers:
                if f.isnil.get(p) != f_prev.isnil.get(p):
                    return False
        if "event" in fields and not isinstance(f.event, NOP):
            return False
        if "pc" in fields and f.pc != f_prev.pc:
            return False
        if "active_child" in fields and not self.default_active_child(f_prev, f_below, f):
            return False
        return True

    def _data_field_candidates(self) -> tuple[str, ...]:
        return self.enum_fields or ()

    # --- C.1 & C.2: Label Initialization ---

    def first_frame(self, f: Frame) -> bool:
        return (f.active and all(not f.active_child[j] for j in range(self.k, self.k + self.m))) or (
            not f.active and all(f.active_child[j] for j in range(self.k, self.k + self.m))
        )

    def start(self, sigma: Label) -> bool:
        self._require_program()
        assert self.root is not None
        f1 = self._frame_at(sigma, 0)
        f2 = self._frame_at(sigma, 1)
        if f1 is None or f2 is None:
            return False
        if not self.initial(sigma):
            return False
        if f2.active != f1.active:
            return False
        if f2.enum_fields != f1.enum_fields:
            return False
        if f2.pc != 0:
            return False
        for p in self.pointers:
            if p != self.root.name and not f2.isnil.get(p, True):
                return False
        if f1.active:
            if not isinstance(f2.event, Here) or f2.event.p != self.root.name:
                return False
            if f2.isnil.get(self.root.name, True):
                return False
            for j in range(self.k, self.k + self.m):
                if f2.active_child.get(j, True):
                    return False
        else:
            if not isinstance(f2.event, NOP):
                return False
            if not f2.isnil.get(self.root.name, False):
                return False
            for j in self.children_keys:
                if f2.active_child.get(j, False):
                    return False
        return True

    def initial(self, sigma: Label) -> bool:
        f2 = self._frame_at(sigma, 1)
        if f2 is None:
            return False
        return f2.prev == (Internal(), 1)

    # --- C.3: Lace Termination ---

    def label_exit(self, sigma: Label, ex_status_set: set[str]) -> bool:
        status = self._label_exit_status(sigma)
        return status in ex_status_set

    def _label_exit_status(self, sigma: Label) -> str:
        frames = self._frames(sigma)
        for f in frames:
            if self.frame_exit(f) == "C":
                return "C"
        for f in frames:
            if self.frame_exit(f) == "E":
                return "E"
        for f in frames:
            if self.frame_exit(f) == "M":
                return "M"
        if any(isinstance(f.event, LOF) for f in frames) or len(sigma) >= self.n + 1:
            return "O"
        return "N"

    def frame_exit(self, f: Frame) -> str:
        self._require_program()
        assert self.function is not None
        if f.pc < len(self.function.instructions):
            if isinstance(self.function.instructions[f.pc], Return):
                return "C"
        if isinstance(f.event, Exit):
            return "C"
        if isinstance(f.event, ERR):
            return "E"
        if isinstance(f.event, OOM):
            return "M"
        return "N"

    def continues(self, f: Frame) -> bool:
        return self.frame_exit(f) == "N"

    # --- C.4: Parent-Child Consistency ---

    def consistent_child(self, parent: Label, child: Label, j: int) -> bool:
        if not self.consistent_first_frames(parent, child, j):
            return False

        self._current_child_key = j
        try:
            ok = True
            for f in self._frames(child):
                if f.prev is None:
                    continue
                dir, a = f.prev
                if isinstance(dir, Down) and dir.child == j:
                    if not self.psi_up(parent, a, child, f.index, f):
                        ok = False
            for f in self._frames(parent):
                if f.prev is None:
                    continue
                dir, a = f.prev
                if isinstance(dir, Up):
                    if not self.psi_down(child, a, parent, f.index, f):
                        ok = False
            return ok
        finally:
            self._current_child_key = None

    def consistent_first_frames(self, parent: Label, child: Label, j: int) -> bool:
        # parent_index = 1 if self.initial(parent) else 0
        pf = self._frame_at(parent, 0)
        cf = self._frame_at(child, 0)
        if pf is None or cf is None:
            return False
        return pf.active_child.get(j) == cf.active

    def psi_internal(self, sigma: Label, a: int, f: Frame) -> bool:
        if not self._len_label(sigma, a):
            return False
        f_prev = self._frame_at(sigma, a)
        if f_prev is None or not self.continues(f_prev):
            return False
        if f.prev != (Internal(), a):
            return False
        sigma_next = sigma.extended_with(f)
        if not self.step(sigma, a, sigma_next, a + 1):
            return False
        return all(not f.upd[p] for p in self.pointers)

    def _expected_upd_external(
        self, leader: Label, follower: Label, direction: Any, f: Frame
    ) -> dict[str, bool] | None:
        if f.index <= 1:
            return {p: False for p in self.pointers}
        try:
            a_ = next(fr.index for fr in self._frames(leader) if fr.prev == (direction, follower.frame.index))
        except StopIteration:
            return None
        expected: dict[str, bool] = {}
        leader_frames = self._frames(leader)
        for p in self.pointers:
            expected[p] = not f.isnil[p] and (
                any(fr.event == Here(p) for fr in leader_frames if fr.index >= a_)
                or any(fr.upd[p] for fr in leader_frames if fr.index >= a_ + 1)
            )
        return expected

    def psi_down(self, parent: Label, a: int, child: Label, b: int, f: Frame) -> bool:
        if not self._len_label(parent, a):
            return False
        f_prev = self._frame_at(parent, a)
        if f_prev is None or not self.continues(f_prev):
            return False
        if not self._len_label(child, b):
            return False
        if f.prev != (Up(), a):
            return False
        if not self.step(parent, a, child, b):
            return False
        child_key = self._current_child_key
        if child_key is None:
            child_key = self._child_key_from_prev(parent, child, b)
        expected = self._expected_upd_external(parent, child, Down(child_key), f)
        if expected is None:
            return False
        return all(f.upd[p] == expected[p] for p in self.pointers)

    def psi_up(self, child: Label, a: int, parent: Label, b: int, f: Frame) -> bool:
        if not self._len_label(child, a):
            return False
        f_prev = self._frame_at(child, a)
        if f_prev is None or not self.continues(f_prev):
            return False
        if not self._len_label(parent, b):
            return False
        if f.prev is None or not isinstance(f.prev[0], Down):
            return False
        if f.prev[1] != a:
            return False
        if not self.step(child, a, parent, b):
            return False
        child_key = self._current_child_key
        f_below = self._frame_at(parent, b - 1)
        if f_below is None:
            return False
        if not self.default_active_child(f_prev, f_below, f):
            return False
        expected = self._expected_upd_external(child, parent, Up(), f)
        if expected is None:
            return False
        return all(f.upd[p] == expected[p] for p in self.pointers)

    # --- C.5: Individual Statements (The "Step" Predicate) ---

    def step(self, sigma: Label, a: int, tau: Label, b: int) -> bool:  # noqa: PLR0911
        self._require_program()
        assert self.function is not None
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if isinstance(f_prev.event, (OOM, ERR, LOF, Exit)):
            return False
        if f_prev.pc >= len(self.function.instructions):
            return self.step_exit(f_prev, f_next)
        inst = self.function.instructions[f_prev.pc]
        if len(sigma) >= self.n and not isinstance(f_next.event, LOF):
            return False

        match inst:
            case IfGoto(ire.PtrIsPtr(p, q), _):
                assert isinstance(p, Var)
                assert isinstance(q, Var)
                return self.step_cmp_ptr(sigma, a, tau, b, p.name, q.name, False)
            case IfGoto():
                return self.step_local_branch(f_prev, f_next, inst.condition, [])
            case Goto():
                return self.step_skip(f_prev, f_next)
            case PtrAssignNil(p):
                return self.step_assgn_nil(f_prev, f_next, p.name)
            case PtrAssignPtr(p, q):
                return self.step_assgn_ptr(sigma, a, tau, b, p.name, q.name)
            case PtrAssignField(p, qfield):
                return self.step_assgn_from_field(sigma, a, tau, b, p.name, qfield.ptr.name, qfield.name)
            case FieldAssignPtr(pfield, q):
                return self.step_assgn_to_field(sigma, a, tau, b, pfield.ptr.name, q.name, pfield.name)
            case VarAssignExpr(d, Field(ptr, name)):
                return self.step_assgn_to_var(sigma, a, tau, b, d.name, ptr.name, name)
            case VarAssignExpr(d, exp):
                return self.step_assgn_exp(f_prev, f_next, d.name, exp)
            case FieldAssignExpr(pfield, exp):
                return self.step_assgn_to_data(sigma, a, tau, b, pfield.ptr.name, exp, pfield.name)
            case FieldAssignNil(pfield):
                return self.step_assgn_to_field_nil(sigma, a, tau, b, pfield.ptr.name, pfield.name)
            case New(p):
                f_next_prev = self._frame_at(tau, b - 1)
                if f_next_prev is None:
                    return False
                return self.step_new(f_prev, f_next_prev, f_next, p.name)
            case Free(p):
                return self.step_free(sigma, a, tau, b, p.name)
            case Return(_):
                return self.step_exit(f_prev, f_next)
            case Skip():
                return self.step_skip(f_prev, f_next)
            case _:
                return False

    def step_exit(self, f_prev: Frame, f_next: Frame) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        if not isinstance(f_next.event, Exit):
            return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "pc", "active_child"},
        )

    def step_skip(self, f_prev: Frame, f_next: Frame) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        if not self.advance_pc(f_prev, f_next):
            return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "event", "active_child"},
        )

    def step_assgn_nil(self, f_prev: Frame, f_next: Frame, p: str) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        if not f_next.isnil.get(p, False):
            return False
        for q in self.pointers:
            if q == p:
                continue
            if f_next.isnil.get(q) != f_prev.isnil.get(q):
                return False
        if not self.advance_pc(f_prev, f_next):
            return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "enum_values", "event", "active_child"},
        )

    def step_assgn_exp(self, f_prev: Frame, f_next: Frame, d: str, exp: Any) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        lab = Label.make(f_prev)
        exp = ppexp(exp, lab)
        if isinstance(exp, EnumConst):
            if f_next.enum_values.get(d) != exp.value:
                return False
        elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
            if f_next.enum_values.get(d) != f_prev.enum_values.get(exp.name):
                return False
        elif sort_of(exp) == BOOL:
            if f_next.enum_values.get(d) not in {"TRUE", "FALSE"}:
                return False
        else:
            # Non-enum values are not tracked; accept the update as-is.
            pass
        for d2 in self.data_vars:
            if d2 == d:
                continue
            if f_next.enum_values.get(d2) != f_prev.enum_values.get(d2):
                return False
        if not self.advance_pc(f_prev, f_next):
            return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "isnil", "event", "active_child"},
        )

    def step_assgn_cond(self, sigma: Label, a: int, tau: Label, b: int, d_bool: str, p: str, q: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if f_prev.isnil[p] or f_prev.isnil[q]:
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            eq_val = f_prev.isnil[p] == f_prev.isnil[q]
            if f_next.enum_values.get(d_bool) != ("TRUE" if eq_val else "FALSE"):
                return False
            for d2 in self.data_vars:
                if d2 == d_bool:
                    continue
                if f_next.enum_values.get(d2) != f_prev.enum_values.get(d2):
                    return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "isnil", "event", "active_child"},
            )
        if self.rewind2(sigma, a, tau, b, p, q):
            return True
        if self.stop_rewind2(sigma, a, p, q):
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            eq_val = self.are_equal_after_rewind(sigma, a, p, q)
            if f_next.enum_values.get(d_bool) != ("TRUE" if eq_val else "FALSE"):
                return False
            for d2 in self.data_vars:
                if d2 == d_bool:
                    continue
                if f_next.enum_values.get(d2) != f_prev.enum_values.get(d2):
                    return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "isnil", "event", "active_child"},
            )
        return False

    def step_assgn_ptr(self, sigma: Label, a: int, tau: Label, b: int, p: str, q: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if f_prev.isnil[q]:
            return self.step_assgn_nil(f_prev, f_next, p)
        if self.rewind(sigma, a, tau, b, q):
            return True
        if self.stop_rewind(sigma, a, q):
            return self.set_ptr_here(f_prev, f_next, p)
        return False

    def step_assgn_to_field(self, sigma: Label, a: int, tau: Label, b: int, p: str, q: str, pfield: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if self.find_or_fail(sigma, a, tau, b, p):
            return True
        if self.stop_rewind(sigma, a, p):
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            if f_prev.isnil[q]:
                if f_next.event != FieldAssignP(pfield, None):
                    return False
            else:
                if f_next.event != FieldAssignP(pfield, q):
                    return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "enum_values", "isnil", "active_child"},
            )
        return False

    def step_assgn_to_field_nil(self, sigma: Label, a: int, tau: Label, b: int, p: str, pfield: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if self.find_or_fail(sigma, a, tau, b, p):
            return True
        if self.stop_rewind(sigma, a, p):
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            if f_next.event != FieldAssignP(pfield, None):
                return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "enum_values", "isnil", "active_child"},
            )
        return False

    def step_assgn_from_field(self, sigma: Label, a: int, tau: Label, b: int, p: str, q: str, pfield: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if f_prev.isnil[q]:
            return self.error(f_prev, f_next)

        if isinstance(f_prev.event, Rewind2):
            i = f_prev.event.i
            r = f_prev.event.p
            if self.points_here(sigma, i, r):
                return self.set_ptr_here(f_prev, f_next, p)
            return self.rewind_special(sigma, a, tau, b, r, i)

        if self.stop_rewind(sigma, a, q):
            if self.is_pfield_nil(sigma, a, pfield) or (
                self.is_pfield_implicit(sigma, a, pfield) and not f_prev.active_child.get(pfield, False)
            ):
                return self.step_assgn_nil(f_prev, f_next, p)
            if self.is_pfield_implicit(sigma, a, pfield) and f_prev.active_child.get(pfield, False):
                if f_next.prev != (Up(), f_prev.index):
                    return False
                if not self.advance_pc(f_prev, f_next):
                    return False
                if not isinstance(f_next.event, Here) or f_next.event.p != p:
                    return False
                if f_next.isnil.get(p, True):
                    return False
                return self._default_fields(
                    f_prev,
                    self._frame_at(tau, b - 1) or f_prev,
                    f_next,
                    {"active", "enum_fields", "enum_values", "isnil", "active_child"},
                )
            for r in self.pointers:
                for i in range(1, len(sigma)):
                    if not self.is_pfield_ptr(sigma, a, pfield, r, i):
                        continue
                    if self.points_here(sigma, i, r):
                        return self.set_ptr_here(f_prev, f_next, p)
                    return self.rewind_special(sigma, a, tau, b, r, i)
        return self.rewind(sigma, a, tau, b, q)

    def step_assgn_to_data(self, sigma: Label, a: int, tau: Label, b: int, p: str, exp: Any, pfield: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if self.find_or_fail(sigma, a, tau, b, p):
            return True
        if self.stop_rewind(sigma, a, p):
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            exp = ppexp(exp, Label.make(f_prev))
            if isinstance(exp, EnumConst):
                if f_next.enum_fields.get(pfield) != exp.value:
                    return False
            elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
                if f_next.enum_fields.get(pfield) != f_prev.enum_fields.get(exp.name):
                    return False
            elif sort_of(exp) == BOOL:
                if f_next.enum_fields.get(pfield) not in {"TRUE", "FALSE"}:
                    return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_values", "isnil", "event", "active_child"},
            )
        return False

    def step_assgn_to_var(
        self, sigma: Label, a: int, tau: Label, b: int, d: str, p: str, pfield: str | None = None
    ) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if self.find_or_fail(sigma, a, tau, b, p):
            return True
        if self.stop_rewind(sigma, a, p):
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            if d in f_prev.enum_values:
                field_name = pfield or (self._data_field_candidates()[0] if self._data_field_candidates() else "val")
                fval = f_prev.enum_fields.get(field_name)
                if f_next.enum_values.get(d) != fval:
                    return False
            for d2 in self.data_vars:
                if d2 == d:
                    continue
                if f_next.enum_values.get(d2) != f_prev.enum_values.get(d2):
                    return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "isnil", "event", "active_child"},
            )
        return False

    def step_new(self, f_prev: Frame, f_next_prev: Frame, f_next: Frame, p: str) -> bool:
        aux_children = range(self.k, self.k + self.m)
        if all(f_prev.active_child[j] for j in aux_children):
            if not isinstance(f_next.event, OOM):
                return False
            if f_next.prev != (Internal(), f_prev.index):
                return False
            return self._default_fields(
                f_prev,
                f_next_prev,
                f_next,
                {"active", "enum_fields", "enum_values", "isnil", "pc", "active_child"},
            )

        j = min(j for j in aux_children if not f_prev.active_child[j])
        if f_next.prev != (Up(), f_prev.index):
            return False
        if not f_next.active:
            return False
        if f_next.isnil.get(p, True):
            return False
        if not isinstance(f_next.event, Here) or f_next.event.p != p:
            return False
        if not self.advance_pc(f_prev, f_next):
            return False
        for i in range(self.k, j):
            if not f_prev.active_child[i]:
                return False
        return self._default_fields(
            f_prev,
            f_next_prev,
            f_next,
            {"enum_fields", "enum_values", "active_child"},
        )

    def step_free(self, sigma: Label, a: int, tau: Label, b: int, p: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if self.find_or_fail(sigma, a, tau, b, p):
            return True
        if self.stop_rewind(sigma, a, p):
            if f_next.prev != (Internal(), f_prev.index):
                return False
            if not self.advance_pc(f_prev, f_next):
                return False
            if f_next.active:
                return False
            for q in self.pointers:
                if self.points_here(sigma, a, q):
                    if not f_next.isnil.get(q, False):
                        return False
                elif f_next.isnil.get(q) != f_prev.isnil.get(q):
                    return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"enum_fields", "enum_values", "event", "active_child"},
            )
        return False

    def step_cmp_ptr(self, sigma: Label, a: int, tau: Label, b: int, p: str, q: str, neg: bool) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if f_prev.isnil[p] or f_prev.isnil[q]:
            cond = xor(neg, f_prev.isnil[p] == f_prev.isnil[q])
            if not self.advance_pc(f_prev, f_next, cond):
                return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "enum_values", "isnil", "event", "active_child"},
            )
        if self.rewind2(sigma, a, tau, b, p, q):
            return True
        if self.stop_rewind2(sigma, a, p, q):
            cond = xor(neg, self.are_equal_after_rewind(sigma, a, p, q))
            if not self.advance_pc(f_prev, f_next, cond):
                return False
            return self._default_fields(
                f_prev,
                self._frame_at(tau, b - 1) or f_prev,
                f_next,
                {"active", "enum_fields", "enum_values", "isnil", "event", "active_child"},
            )
        return False

    def step_local_branch(self, f_prev: Frame, f_next: Frame, r: Any, exprs: List[Any]) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        cond_expr = r if isinstance(r, Expr) else None
        if cond_expr is None and exprs:
            cond_expr = exprs[0] if isinstance(exprs[0], Expr) else None
        if cond_expr is None:
            return False
        cond_eval = ppexp(cond_expr, f_prev)
        if cond_eval == ire.TRUE:
            if not self.advance_pc(f_prev, f_next, True):
                return False
        elif cond_eval == ire.FALSE:
            if not self.advance_pc(f_prev, f_next, False):
                return False
        else:
            if not self.advance_pc(f_prev, f_next, True) and not self.advance_pc(f_prev, f_next, False):
                return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "event", "active_child"},
        )

    def advance_pc(self, f_prev: Frame, f_next: Frame, condition: Any = None) -> bool:
        self._require_program()
        assert self.function is not None
        info = self.function.info_at(f_prev.pc)
        if condition is None:
            if not isinstance(info.next_pc, int):
                return False
            return f_next.pc == info.next_pc
        if not isinstance(info.next_pc, tuple):
            return False
        return f_next.pc == (info.next_pc[0] if condition else info.next_pc[1])

    def default(self, f_prev: Frame, f_below: Frame, f_current: Frame) -> bool:
        return self._default_fields(
            f_prev,
            f_below,
            f_current,
            {"active", "enum_fields", "enum_values", "isnil", "event", "pc", "active_child"},
        )

    def default_active_child(self, f_prev: Frame, f_below: Frame, f_current: Frame) -> bool:
        if f_current.prev is None:
            return False
        dir, _ = f_current.prev
        if isinstance(dir, Down):
            j = dir.child
            if f_current.active_child.get(j) != f_prev.active:
                return False
            for i in self.children_keys:
                if i == j:
                    continue
                if f_current.active_child.get(i) != f_below.active_child.get(i):
                    return False
            return True
        for i in self.children_keys:
            if f_current.active_child.get(i) != f_below.active_child.get(i):
                return False
        return True

    def set_ptr_here(self, f_prev: Frame, f_next: Frame, p: str) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        if not self.advance_pc(f_prev, f_next):
            return False
        if not isinstance(f_next.event, Here) or f_next.event.p != p:
            return False
        if f_next.isnil.get(p, True):
            return False
        for q in self.pointers:
            if q == p:
                continue
            if f_next.isnil.get(q) != f_prev.isnil.get(q):
                return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "enum_values", "active_child"},
        )

    def error(self, f_prev: Frame, f_next: Frame) -> bool:
        if f_next.prev != (Internal(), f_prev.index):
            return False
        if not isinstance(f_next.event, ERR):
            return False
        return self._default_fields(
            f_prev,
            f_prev,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "pc", "active_child"},
        )

    # --- C.5 & C.7: Helpers for Field Access ---

    def is_pfield_nil(self, sigma: Label, a: int, pfield: str) -> bool:
        frames = [f for f in self._frames(sigma) if f.index <= a]
        for i, f in enumerate(frames):
            if f.event == FieldAssignP(pfield, None):
                if all(not isinstance(fr.event, FieldAssignP) or fr.event.pfield != pfield for fr in frames[i + 1 :]):
                    return True
        return False

    def is_pfield_ptr(self, sigma: Label, a: int, pfield: str, r: str, i: int) -> bool:
        fi = self._frame_at(sigma, i)
        if fi is None or fi.event != FieldAssignP(pfield, r):
            return False
        frames = [f for f in self._frames(sigma) if i < f.index <= a]
        return all(not isinstance(fr.event, FieldAssignP) or fr.event.pfield != pfield for fr in frames)

    def is_pfield_implicit(self, sigma: Label, a: int, pfield: str) -> bool:
        frames = [f for f in self._frames(sigma) if 1 <= f.index <= a]
        return all(not isinstance(fr.event, FieldAssignP) or fr.event.pfield != pfield for fr in frames)

    # --- C.7: Rewinding the Lace ---

    def find_or_fail(self, sigma: Label, a: int, tau: Label, b: int, p: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        if f_prev is None or f_next is None:
            return False
        if f_prev.isnil.get(p, False):
            return self.error(f_prev, f_next)
        return self.rewind(sigma, a, tau, b, p)

    def rewind(self, sigma: Label, a: int, tau: Label, b: int, q: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        f_below = self._frame_at(tau, b - 1)
        if f_prev is None or f_next is None or f_below is None:
            return False
        if f_prev.isnil.get(q, False):
            return False
        a_ = self.cur_rewind_pos(sigma, a)
        if self.points_here(sigma, a_, q):
            return False
        a__ = self.last_upd(sigma, a_, q)
        prev = self._frame_at(sigma, a__)
        if prev is None or prev.prev is None:
            return False
        dir, b_prev = prev.prev
        if not isinstance(f_next.event, Rewind) or f_next.event.i != b_prev:
            return False
        if f_next.prev is None or f_next.prev[1] != a:
            return False
        if not are_opposite_directions(dir, f_next.prev[0]):
            return False
        return self._default_fields(
            f_prev,
            f_below,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "pc", "active_child"},
        )

    def rewind2(self, sigma: Label, a: int, tau: Label, b: int, q1: str, q2: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        f_below = self._frame_at(tau, b - 1)
        if f_prev is None or f_next is None or f_below is None:
            return False
        if f_prev.isnil.get(q1, False) or f_prev.isnil.get(q2, False):
            return False
        a_ = self.cur_rewind_pos(sigma, a)
        if self.points_here(sigma, a_, q1) or self.points_here(sigma, a_, q2):
            return False
        a__ = max(self.last_upd(sigma, a_, q1), self.last_upd(sigma, a_, q2))
        prev = self._frame_at(sigma, a__)
        if prev is None or prev.prev is None:
            return False
        dir, b_prev = prev.prev
        if not isinstance(f_next.event, Rewind) or f_next.event.i != b_prev:
            return False
        if f_next.prev is None or f_next.prev[1] != a:
            return False
        if not are_opposite_directions(dir, f_next.prev[0]):
            return False
        return self._default_fields(
            f_prev,
            f_below,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "pc", "active_child"},
        )

    def rewind_special(self, sigma: Label, a: int, tau: Label, b: int, r: str, i: int) -> bool:
        f_prev = self._frame_at(sigma, a)
        f_next = self._frame_at(tau, b)
        f_below = self._frame_at(tau, b - 1)
        if f_prev is None or f_next is None or f_below is None:
            return False
        if f_prev.isnil.get(r, False):
            return False
        if self.points_here(sigma, i, r):
            return False
        a__ = self.last_upd(sigma, i, r)
        prev = self._frame_at(sigma, a__)
        if prev is None or prev.prev is None:
            return False
        dir, b_prev = prev.prev
        if not isinstance(f_next.event, Rewind2) or f_next.event.i != b_prev or f_next.event.p != r:
            return False
        if f_next.prev is None or f_next.prev[1] != a:
            return False
        if not are_opposite_directions(dir, f_next.prev[0]):
            return False
        return self._default_fields(
            f_prev,
            f_below,
            f_next,
            {"active", "enum_fields", "enum_values", "isnil", "pc", "active_child"},
        )

    def stop_rewind(self, sigma: Label, a: int, q: str) -> bool:
        f_prev = self._frame_at(sigma, a)
        if f_prev is None or f_prev.isnil.get(q, True):
            return False
        a_ = self.cur_rewind_pos(sigma, a)
        return self.points_here(sigma, a_, q)

    def stop_rewind2(self, sigma: Label, a: int, q1: str, q2: str) -> bool:
        return self.stop_rewind(sigma, a, q1) or self.stop_rewind(sigma, a, q2)

    def cur_rewind_pos(self, sigma: Label, a: int) -> int:
        f = self._frame_at(sigma, a)
        if f is None:
            return a
        if isinstance(f.event, Rewind):
            return f.event.i
        if isinstance(f.event, Rewind2):
            return f.event.i
        return a

    def points_here(self, sigma: Label, a: int, q: str) -> bool:
        frames = [f for f in self._frames(sigma) if 1 <= f.index <= a]
        for f in reversed(frames):
            if isinstance(f.event, Here) and f.event.p == q:
                return True
            if f.upd.get(q, False):
                return False
        return False

    def last_upd(self, sigma: Label, a: int, q: str) -> int:
        indices = [f.index for f in self._frames(sigma) if 1 <= f.index <= a and f.upd.get(q, False)]
        return max(indices) if indices else 1

    def last_visit(self, tau: Label, direction: Any, j: int) -> int:
        indices = [
            f.index for f in self._frames(tau) if f.prev is not None and f.prev[0] == direction and f.prev[1] <= j
        ]
        return max(indices) if indices else 0

    def are_equal_after_rewind(self, sigma: Label, a: int, p: str, q: str) -> bool:
        a_ = self.cur_rewind_pos(sigma, a)
        return self.points_here(sigma, a_, p) and self.points_here(sigma, a_, q)

    # def is_consistent_CHC_I(pair: Pair) -> bool: ...

    # def is_consistent_verify_CHC_II(pair: Pair) -> bool: ...

    def _child_key_from_prev(self, parent: Label, child: Label, child_index: int) -> str | int:
        # Best-effort: use known child keys if parent has a frame that came from child.
        for f in self._frames(parent):
            if f.prev is None:
                continue
            dir, idx = f.prev
            if isinstance(dir, Down) and idx == child_index:
                return dir.child
        # Fallback to auxiliary child 0 if unknown (keeps verification conservative).
        return self.indexed_children_keys[0] if self.indexed_children_keys else ""

    def is_consistent_verify_CHC_III(self, pair: Pair) -> bool:
        sigma = pair.leader()
        if len(sigma) < 2:
            return False
        a = len(sigma) - 2
        f = self._frame_at(sigma, a + 1)
        if f is None:
            return False
        sigma_prefix = self._label_prefix(sigma, a)
        return self.psi_internal(sigma_prefix, a, f)

    def is_consistent_verify_CHC_IV(self, pair: Pair) -> bool:
        parent = pair.parent
        child = pair.child
        if len(parent) < 2:
            return False
        b = len(parent) - 1
        f = self._frame_at(parent, b)
        if f is None or f.prev is None:
            return False
        if not isinstance(f.prev[0], Down) or f.prev[0].child != pair.child_key:
            return False
        a = len(child) - 1
        parent_prefix = self._label_prefix(parent, b - 1)
        if not self.consistent_child(parent_prefix, child, pair.child_key):
            return False
        return self.psi_up(child, a, parent, b, f)

    def is_consistent_verify_CHC_V(self, pair: Pair) -> bool:
        parent = pair.parent
        child = pair.child
        if len(child) < 2:
            return False
        b = len(child) - 1
        f = self._frame_at(child, b)
        if f is None:
            return False
        if f.prev != (Up(), len(parent) - 1):
            return False
        a = len(parent) - 1
        child_prefix = self._label_prefix(child, b - 1)
        if not self.consistent_child(parent, child_prefix, pair.child_key):
            return False
        return self.psi_down(parent, a, child, b, f)

    def verify_pair(self, pair: Pair) -> bool:
        leader = pair.leader()
        if len(leader) <= 2:
            return True
        last = leader[-1]
        if last.prev is None:
            return True
        direction, _ = last.prev
        if isinstance(direction, Internal):
            return self.is_consistent_verify_CHC_III(pair)
        if isinstance(direction, Down):
            return self.is_consistent_verify_CHC_IV(pair)
        if isinstance(direction, Up):
            return self.is_consistent_verify_CHC_V(pair)
        return False
