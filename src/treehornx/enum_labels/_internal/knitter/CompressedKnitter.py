from dataclasses import dataclass
from typing import Callable, Iterable, cast

from frozendict import frozendict

import treehornx.ir.expressions as ire
from treehornx.enum_labels.core.Dir import *
from treehornx.enum_labels.core.Event import *
from treehornx.enum_labels.core.Frame import Frame, FrameDescriptor
from treehornx.enum_labels.core.Label import Label
from treehornx.enum_labels.utils import normalized_expr
from treehornx.ir.function import Function
from treehornx.ir.instructions import *

from .IKnitter import IKnitter
from .KnitResult import ExternalStepResult, InternalStepResult, KnitResult, StepFailed
from .Pair import LeadershipKind, Pair
from .StepKind import StepKind


def is_pfield_nil(sigma: Label, pfield: str) -> bool:
    frames = sigma[1:]
    for f in reversed(frames):
        for event in f.events:
            match event:
                case FieldAssignP(pf, p) if pf == pfield:
                    return p is None
                case FieldHere(pf) if pf == pfield:
                    return False
                case _:
                    continue

    return False


def is_pfield_ptr(sigma: Label, a: int, pfield: str, r: str, i: int) -> bool:
    frames = sigma[i + 1 : a + 1]
    for f in reversed(frames):
        for event in f.events:
            match event:
                case FieldAssignP(pf, _) | FieldHere(pf) if pf == pfield:
                    return False
                case _:
                    continue

    return any(event == FieldAssignP(pfield, r) for event in sigma[i].events)


def is_pfield_implicit(sigma: Label, pfield: str) -> bool:
    for f in sigma[1:]:
        for event in f.events:
            match event:
                case FieldAssignP(pf, _) | FieldHere(pf) if pf == pfield:
                    return False
                case _:
                    continue

    return True


def is_pfield_here(sigma: Label, pfield: str) -> bool:
    for f in reversed(sigma[1:]):
        for event in f.events:
            match event:
                case FieldHere(pf) if pf == pfield:
                    return True
                case FieldAssignP(pf, _) if pf == pfield:
                    return False
                case _:
                    continue

    return False


def cur_rewind_pos(sigma: Label) -> int:
    if not sigma.frame.events:
        return len(sigma) - 1
    for event in sigma.frame.events:
        match event:
            case Rewind(b):
                return b
            case _:
                return len(sigma) - 1
    assert False, "cur_rewind_pos should always find a Rewind event in the current frame"


def points_here(sigma: Label, a: int, q: str) -> bool:
    for f in reversed(sigma[1 : a + 1]):
        for event in f.events:
            match event:
                case Here(p) if p == q:
                    return True
                case _ if f.upd[q]:
                    return False
                case _:
                    continue

    return False


def are_equal_after_rewind(sigma: Label, p: str, q: str) -> bool:
    a_ = cur_rewind_pos(sigma)
    return points_here(sigma, a_, p) and points_here(sigma, a_, q)


def last_upd(sigma: Label, a: int, q: str) -> int:
    upd_q_indices = {f.index for f in sigma[1 : a + 1] if f.upd[q]}
    return max(upd_q_indices) if upd_q_indices else 1


def stop_rewind(sigma: Label, q: str) -> bool:
    a_ = cur_rewind_pos(sigma)
    return not sigma.frame.isnil[q] and points_here(sigma, a_, q)


def stop_rewind2(sigma: Label, q1: str, q2: str) -> bool:
    return stop_rewind(sigma, q1) or stop_rewind(sigma, q2)


def default_active_child(fprev: Frame, fbelow: Frame, f: FrameDescriptor) -> FrameDescriptor:
    assert f.prev is not None
    match f.prev:
        case Down(j), _:
            f.active_child[j] = fprev.active
            for i in filter(lambda i: i != j, fbelow.active_child.keys()):
                f.active_child[i] = fbelow.active_child[i]
        case _:
            f.active_child = dict(fbelow.active_child)
    return f


def _default_prototype(
    fprev: Frame, fbelow: Frame, f: FrameDescriptor, default_fields: set[str] = set()
) -> FrameDescriptor:
    """Create a default frame based on the previous frame and the frame below. It set to default all the fields."""
    if "active" in default_fields:
        f.active = fbelow.active
    if "val" in default_fields:
        f.enum_fields = dict(fbelow.enum_fields)
    if "d" in default_fields:
        f.enum_values = dict(fprev.enum_vars)
    if "isnil" in default_fields:
        f.isnil = dict(fprev.isnil)
    if "event" in default_fields:
        f.event = NOP()
    if "pc" in default_fields:
        f.pc = fprev.pc
    if "active_child" in default_fields:
        f = default_active_child(fprev, fbelow, f)
    return f


def default(*default_fields: str) -> Callable[[Frame, Frame, FrameDescriptor], FrameDescriptor]:
    """Create a default frame based on the previous frame and the frame below.
    It set to default all the fields in default_fields."""

    assert all(field in {"active", "val", "d", "isnil", "event", "pc", "active_child"} for field in default_fields), (
        f"Invalid default field. Valid fields are: active, event, d, val, isnil, pc, active_child. Got: {default_fields}"
    )

    def _default(fprev: Frame, fbelow: Frame, f: FrameDescriptor) -> FrameDescriptor:
        return _default_prototype(fprev, fbelow, f, set(default_fields))

    return _default


def set_ptr_here(f1: Frame, f2: FrameDescriptor, p: str) -> FrameDescriptor:
    f2.pc = f1.pc + 1
    f2.event = Here(p)
    f2.isnil[p] = False
    f2 = default("active", "val", "d", "active_child")(f1, f1, f2)
    return f2


class NonContinuosPairError(Exception):
    pass


@dataclass
class CompressedKnitter(IKnitter):
    function: Function
    k: int
    m: int
    n: int
    make_label: Callable[[Label | None, Frame], Label] = lambda o, f: Label(f, o)

    def pointers(self) -> Iterable[str]:
        for p in self.function.vars:
            if p.sort.is_ptr():
                yield p.name

    def advance_pc(self, f1: Frame, f2: FrameDescriptor, truthy: bool | None = None) -> FrameDescriptor:
        if truthy is None:
            next_pc = self.function.info_at(f1.pc).next_pc
            assert isinstance(next_pc, int)
            f2.pc = next_pc
        else:
            next_pc = self.function.info_at(f1.pc).next_pc
            assert isinstance(next_pc, tuple)
            f2.pc = next_pc[0] if truthy else next_pc[1]
        return f2

    def _copy_all_isnil_but_target(self, f1: Frame, f2: FrameDescriptor, target: str) -> FrameDescriptor:
        for p in self.pointers():
            if p != target:
                f2.isnil[p] = f1.isnil[p]
        return f2

    def _copy_all_active_child_but_target(self, f1: Frame, f2: FrameDescriptor, target: str | int) -> FrameDescriptor:
        for child in f1.active_child:
            if child != target:
                f2.active_child[child] = f1.active_child[child]
        return f2

    def _copy_all_enum_d_but_target(self, f1: Frame, f2: FrameDescriptor, target: str) -> FrameDescriptor:
        for d in f1.enum_vars:
            if d != target:
                f2.enum_values[d] = f1.enum_vars[d]
        return f2

    def _copy_all_enum_val_but_target(self, f1: Frame, f2: FrameDescriptor, target: str) -> FrameDescriptor:
        for d in f1.enum_fields:
            if d != target:
                f2.enum_fields[d] = f1.enum_fields[d]
        return f2

    def _prev_of_external_step(self, pair: Pair) -> tuple[Dir, int]:
        return (pair.rev_dir(), pair.leader().frame.index)

    def _prev_of_internal_step(self, last_frame: Frame) -> tuple[Dir, int]:
        if self._replace_last_frame(last_frame):
            return (Internal(), last_frame.index)
        else:
            return (Internal(), last_frame.index + 1)

    def set_ptr_here(self, f1: Frame, p: str) -> FrameDescriptor:
        f2 = FrameDescriptor()
        f2 = self._copy_all_isnil_but_target(f1, f2, p)
        f2.prev = self._prev_of_internal_step(f1)
        return set_ptr_here(f1, f2, p)

    def rewind(self, pair: Pair, q: str) -> FrameDescriptor:
        sigma = pair.leader()
        tau = pair.follower()
        assert not sigma.frame.isnil[q]
        a_ = cur_rewind_pos(sigma)
        assert not points_here(sigma, a_, q)
        a__ = last_upd(sigma, a_, q)
        dir, b_ = sigma[a__].prev  # type: ignore
        if dir != pair.dir():
            raise NonContinuosPairError()
        assert isinstance(b_, int)
        tau_b = FrameDescriptor()
        tau_b.event = Rewind(b_)
        tau_b.prev = self._prev_of_external_step(pair)
        tau_b = default("active", "val", "d", "isnil", "pc", "active_child")(sigma.frame, tau.frame, tau_b)
        return tau_b

    def rewind2(self, pair: Pair, p: str, q: str) -> FrameDescriptor:
        prewind = self.rewind(pair, p)
        qrewind = self.rewind(pair, q)
        assert isinstance(prewind.event, Rewind)
        assert isinstance(qrewind.event, Rewind)
        i = max(prewind.event.i, qrewind.event.i)
        prewind.event = Rewind(i)
        prewind.prev = self._prev_of_external_step(pair)
        return prewind

    def rewind_special(self, pair: Pair, r: str, a_: int) -> FrameDescriptor:
        sigma = pair.leader()
        tau = pair.follower()
        a__ = last_upd(sigma, a_, r)
        dir, b_ = sigma[a__].prev  # type: ignore
        if dir != pair.dir():
            raise NonContinuosPairError()
        assert isinstance(b_, int)
        tau_b = FrameDescriptor()
        tau_b.event = Rewind2(b_, r)
        tau_b.prev = self._prev_of_external_step(pair)
        tau_b = default("active", "val", "d", "isnil", "pc", "active_child")(sigma.frame, tau.frame, tau_b)
        return tau_b

    def error(self, f1: Frame) -> FrameDescriptor:
        f2 = FrameDescriptor()
        f2.event = ERR()
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "d", "isnil", "pc", "active_child")(f1, f1, f2)
        return f2

    def oom(self, f1: Frame) -> FrameDescriptor:
        f2 = FrameDescriptor()
        f2.event = OOM()
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "d", "isnil", "pc", "active_child")(f1, f1, f2)
        return f2

    def label_overflow(self, f1: Frame) -> FrameDescriptor:
        f2 = FrameDescriptor()
        f2.event = LOF()
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "d", "isnil", "pc", "active_child")(f1, f1, f2)
        return f2

    def step_skip(self, sigma: Label) -> FrameDescriptor:
        f1 = sigma.frame
        f2 = FrameDescriptor()
        f2 = self.advance_pc(f1, f2)
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "d", "isnil", "event", "active_child")(f1, f1, f2)
        return f2

    def step_assign_nil(self, sigma: Label, p: str) -> FrameDescriptor:
        f1 = sigma.frame
        f2 = FrameDescriptor()
        f2 = self.advance_pc(f1, f2)
        f2.isnil[p] = True
        f2 = self._copy_all_isnil_but_target(f1, f2, p)
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "d", "event", "active_child")(f1, f1, f2)
        return f2

    def step_var_assign_exp(self, f1: Frame, d: Var, exp: Expr) -> tuple[FrameDescriptor, FrameDescriptor | None]:
        f2 = FrameDescriptor()
        f2 = self.advance_pc(f1, f2)
        f2 = self._copy_all_enum_d_but_target(f1, f2, d.name)
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "isnil", "event", "active_child")(f1, f1, f2)
        exp = normalized_expr(exp, f1)
        if isinstance(exp, ire.EnumConst):
            assert isinstance(exp, ire.EnumConst)
            f2.enum_values[d.name] = exp.variant
            return f2, None
        elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
            flag_name = f1.enum_vars[exp.name]
            f2.enum_values[d.name] = flag_name
            return f2, None
        elif sort_of(d) == BOOL:
            f2_true = f2
            f2_false = deepcopy(f2)
            f2_true.enum_values[d.name] = "TRUE"
            f2_false.enum_values[d.name] = "FALSE"
            return f2_true, f2_false
        else:
            return f2, None

    def step_new(self, pair: Pair, p: str) -> tuple[FrameDescriptor, StepKind]:
        f = pair.leader().frame
        # OOM
        if all(f.active_child[j] for j in range(self.k, self.k + self.m)):
            return self.oom(f), StepKind.INTERNAL

        # normal case
        f_ = pair.follower().frame
        f__ = FrameDescriptor()

        j = min(j for j in range(self.k, self.k + self.m) if not f.active_child[j])
        if pair.dir() != Down(j):
            raise NonContinuosPairError()
        f__.isnil[p] = False
        f__ = self._copy_all_isnil_but_target(f, f__, p)
        f__.event = Here(p)
        f__.active = True
        f__ = self.advance_pc(f, f__)
        f__.prev = self._prev_of_external_step(pair)
        f__ = default("val", "d", "active_child")(f, f_, f__)
        return f__, StepKind.EXTERNAL

    def step_local_branch(self, sigma: Label) -> tuple[FrameDescriptor | None, FrameDescriptor | None]:
        f1 = sigma.frame
        inst = self.function.instructions[f1.pc]
        assert isinstance(inst, IfGoto)
        expr = inst.condition
        expr = normalized_expr(expr, f1)
        ftrue, ffalse = None, None
        if expr == ire.TRUE or expr != ire.FALSE:
            ftrue = FrameDescriptor()
            ftrue = self.advance_pc(f1, ftrue, True)
            ftrue.prev = self._prev_of_internal_step(f1)
            ftrue = default("active", "val", "d", "isnil", "event", "active_child")(f1, f1, ftrue)
        if expr == ire.FALSE or expr != ire.TRUE:
            ffalse = FrameDescriptor()
            ffalse = self.advance_pc(f1, ffalse, False)
            ffalse.prev = self._prev_of_internal_step(f1)
            ffalse = default("active", "val", "d", "isnil", "event", "active_child")(f1, f1, ffalse)
        return ftrue, ffalse

    def step_assign_cond(self, sigma: Label, tau: Label, p: str, q: str) -> tuple[FrameDescriptor, StepKind]:
        raise NotImplementedError("step_assign_cond not implemented yet")

    def step_ptr_assign_ptr(self, pair: Pair, p: str, q: str) -> tuple[FrameDescriptor, StepKind]:
        # p = q
        sigma = pair.leader()
        if sigma.frame.isnil[q]:
            return self.step_assign_nil(sigma, p), StepKind.INTERNAL
        elif stop_rewind(sigma, q):
            return self.set_ptr_here(sigma.frame, p), StepKind.INTERNAL
        else:
            return self.rewind(pair, q), StepKind.EXTERNAL

    def step_field_assign_ptr(self, pair: Pair, p: str, q: str, pfield: str) -> tuple[FrameDescriptor, StepKind]:
        """p->pfield := q"""
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma.frame), StepKind.INTERNAL

        elif stop_rewind(sigma, p):
            sigma_a = FrameDescriptor()
            sigma_a = self.advance_pc(sigma.frame, sigma_a)
            if points_here(sigma, len(sigma) - 1, q):
                sigma_a.event = FieldHere(pfield)
            else:
                sigma_a.event = FieldAssignP(pfield, None if sigma.frame.isnil[q] else q)
            sigma_a.prev = self._prev_of_internal_step(sigma.frame)
            sigma_a = default("active", "val", "d", "isnil", "active_child")(sigma.frame, sigma.frame, sigma_a)
            return sigma_a, StepKind.INTERNAL

        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_field_assign_exp(
        self, pair: Pair, p: str, pfield: str, exp: Expr
    ) -> tuple[FrameDescriptor, FrameDescriptor | None, StepKind]:
        """p->pfield := exp"""
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma.frame), None, StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            exp = normalized_expr(exp, sigma.frame)
            if sort_of(exp).is_enum():
                if isinstance(exp, (ire.EnumConst, ire.Var)):  # enum values
                    tau_b = FrameDescriptor()
                    tau_b = self.advance_pc(sigma.frame, tau_b)
                    match exp:
                        case ire.EnumConst(variant=variant, value=_):
                            tau_b.enum_fields[pfield] = variant
                        case ire.Var(name=name):
                            flag_name = sigma.frame.enum_fields[name]
                            tau_b.enum_fields[pfield] = flag_name
                    tau_b = self._copy_all_enum_val_but_target(sigma.frame, tau_b, pfield)
                    tau_b.prev = self._prev_of_internal_step(sigma.frame)
                    tau_b = default("active", "d", "isnil", "event", "active_child")(sigma.frame, sigma.frame, tau_b)
                    return tau_b, None, StepKind.INTERNAL

                elif sort_of(exp) == BOOL:  # boolean expressions
                    tau_b = FrameDescriptor()
                    tau_b = self.advance_pc(sigma.frame, tau_b)
                    tau_b_true = tau_b
                    tau_b.prev = self._prev_of_internal_step(sigma.frame)
                    tau_b = default("active", "d", "isnil", "event", "active_child")(sigma.frame, sigma.frame, tau_b)
                    tau_b_false = deepcopy(tau_b)
                    tau_b_true.enum_fields[pfield] = "TRUE"
                    tau_b_false.enum_fields[pfield] = "FALSE"
                    tau_b_true = self._copy_all_enum_val_but_target(sigma.frame, tau_b_true, pfield)
                    tau_b_false = self._copy_all_enum_val_but_target(sigma.frame, tau_b_false, pfield)

                    return tau_b_true, tau_b_false, StepKind.INTERNAL
                else:
                    raise RuntimeError(
                        f"Unsupported expression type in step_field_assign_exp: {exp} with sort {sort_of(exp)}"
                    )

            else:
                tau_b = FrameDescriptor()
                tau_b = self.advance_pc(sigma.frame, tau_b)
                tau_b = self._copy_all_enum_val_but_target(sigma.frame, tau_b, pfield)
                tau_b.prev = self._prev_of_internal_step(sigma.frame)
                tau_b = default("active", "d", "isnil", "event", "active_child")(sigma.frame, sigma.frame, tau_b)
                return tau_b, None, StepKind.INTERNAL

        else:
            return self.rewind(pair, p), None, StepKind.EXTERNAL

    def step_var_assign_field(self, pair: Pair, var: str, p: str, pfield: str) -> tuple[FrameDescriptor, StepKind]:
        """var := p->field"""
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma.frame), StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            tau_b = FrameDescriptor()
            tau_b = self.advance_pc(sigma.frame, tau_b)
            if var in sigma.frame.enum_vars:
                flag_name = sigma.frame.enum_fields[pfield]
                tau_b.enum_values[var] = flag_name
            tau_b = self._copy_all_enum_d_but_target(sigma.frame, tau_b, var)
            tau_b.prev = self._prev_of_internal_step(sigma.frame)
            tau_b = default("active", "val", "isnil", "event", "active_child")(sigma.frame, sigma.frame, tau_b)
            return tau_b, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_free(self, pair: Pair, p: str) -> tuple[FrameDescriptor, StepKind]:
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma.frame), StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            tau_b = FrameDescriptor()
            tau_b.active = False
            tau_b = self.advance_pc(sigma.frame, tau_b)
            for q in self.pointers():
                if points_here(sigma, len(sigma) - 1, q):
                    tau_b.isnil[q] = True
                else:
                    tau_b.isnil[q] = sigma.frame.isnil[q]
            tau_b = self._copy_all_isnil_but_target(sigma.frame, tau_b, p)
            tau_b.prev = self._prev_of_internal_step(sigma.frame)
            tau_b = default("val", "d", "event", "active_child")(sigma.frame, sigma.frame, tau_b)
            return tau_b, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_cmp_ptr(self, pair: Pair, p: str, q: str) -> tuple[FrameDescriptor, StepKind]:
        sigma = pair.leader()
        isnil_p = sigma.frame.isnil[p]
        isnil_q = sigma.frame.isnil[q]
        if isnil_p or isnil_q:
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, tuple)
            ftrue = FrameDescriptor()
            ftrue = self.advance_pc(sigma.frame, ftrue, isnil_p == isnil_q)
            ftrue.prev = self._prev_of_internal_step(sigma.frame)
            ftrue = default("active", "val", "d", "isnil", "event", "active_child")(sigma.frame, sigma.frame, ftrue)
            return ftrue, StepKind.INTERNAL
        elif stop_rewind2(sigma, p, q):
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, tuple)
            frame = FrameDescriptor()
            frame = self.advance_pc(sigma.frame, frame, are_equal_after_rewind(sigma, p, q))
            frame.prev = self._prev_of_internal_step(sigma.frame)
            frame = default("active", "val", "d", "isnil", "event", "active_child")(sigma.frame, sigma.frame, frame)
            return frame, StepKind.INTERNAL
        else:
            frame = self.rewind2(pair, p, q)
            return frame, StepKind.EXTERNAL

    def step_ptr_assign_field(self, pair: Pair, p: str, pfield: str, q: str) -> tuple[FrameDescriptor, StepKind]:
        """p := q->pfield"""
        sigma = pair.leader()
        tau = pair.follower()
        if sigma.frame.isnil[q]:
            return self.error(sigma.frame), StepKind.INTERNAL

        rewind2_event = next((e for e in sigma.frame.events if isinstance(e, Rewind2)), None)
        if rewind2_event is not None:
            i = rewind2_event.i
            r = rewind2_event.p
            if points_here(sigma, i, r):
                return self.set_ptr_here(sigma.frame, p), StepKind.INTERNAL
            else:
                return self.rewind_special(pair, r, i), StepKind.EXTERNAL
        elif stop_rewind(sigma, q):
            if is_pfield_nil(sigma, pfield) or (
                is_pfield_implicit(sigma, pfield) and not sigma.frame.active_child[pfield]
            ):
                return self.step_assign_nil(sigma, p), StepKind.INTERNAL
            elif is_pfield_implicit(sigma, pfield) and sigma.frame.active_child[pfield]:
                if pair.dir() != Down(pfield):
                    raise NonContinuosPairError()
                tau_b = FrameDescriptor()
                tau_b.isnil[p] = False
                tau_b = self._copy_all_isnil_but_target(sigma.frame, tau_b, p)
                tau_b = self.advance_pc(sigma.frame, tau_b)
                tau_b.event = Here(p)
                tau_b.prev = self._prev_of_external_step(pair)
                tau_b = default("active", "val", "d", "active_child")(sigma.frame, tau.frame, tau_b)
                return tau_b, StepKind.EXTERNAL
            else:
                for r in self.pointers():
                    for i in range(1, len(sigma)):
                        if is_pfield_here(sigma, pfield):
                            return self.set_ptr_here(sigma.frame, p), StepKind.INTERNAL
                        if is_pfield_ptr(sigma, len(sigma) - 1, pfield, r, i):
                            return self.rewind_special(pair, r, i), StepKind.EXTERNAL
                assert False, "Unreachable code in step_ptr_assign_field"
        else:
            return self.rewind(pair, q), StepKind.EXTERNAL

    def step_exit(self, sigma: Label) -> FrameDescriptor:
        f1 = sigma.frame
        f2 = FrameDescriptor()
        f2.event = Exit()
        f2.prev = self._prev_of_internal_step(f1)
        f2 = default("active", "val", "d", "isnil", "pc", "active_child")(f1, f1, f2)
        return f2

    def step(self, pair: Pair) -> tuple[FrameDescriptor, FrameDescriptor | None, StepKind] | None:
        try:
            pc = pair.leader().frame.pc
            if pc >= len(self.function.instructions):
                return self.step_exit(pair.leader()), None, StepKind.INTERNAL
            inst = self.function.instructions[pc]
            if len(pair.leader()) >= self.n:
                return self.label_overflow(pair.leader().frame), None, StepKind.INTERNAL
            match inst:
                case IfGoto(ire.PtrIsPtr(p, q), _):
                    assert isinstance(p, Var)
                    assert isinstance(q, Var)
                    frame, kind = self.step_cmp_ptr(pair, p.name, q.name)
                    return frame, None, kind
                case IfGoto():
                    ftrue, ffalse = self.step_local_branch(pair.leader())
                    if ftrue and ffalse:
                        return ftrue, ffalse, StepKind.INTERNAL
                    elif ftrue:
                        return ftrue, None, StepKind.INTERNAL
                    elif ffalse:
                        return ffalse, None, StepKind.INTERNAL
                    else:
                        raise RuntimeError("No valid branch in step_local_branch")
                case Goto():
                    frame = self.step_skip(pair.leader())
                    return frame, None, StepKind.INTERNAL
                case PtrAssignNil(p):
                    frame = self.step_assign_nil(pair.leader(), p.name)
                    return frame, None, StepKind.INTERNAL
                case PtrAssignPtr(p, q):
                    frame, kind = self.step_ptr_assign_ptr(pair, p.name, q.name)
                    return frame, None, kind
                case PtrAssignField(p, qfield):
                    frame, kind = self.step_ptr_assign_field(pair, p.name, qfield.name, qfield.ptr.name)
                    return frame, None, kind
                case FieldAssignPtr(pfield, q):
                    frame, kind = self.step_field_assign_ptr(pair, pfield.ptr.name, q.name, pfield.name)
                    return frame, None, kind
                case VarAssignExpr(d, Field(ptr, name)):
                    frame, kind = self.step_var_assign_field(pair, d.name, ptr.name, name)
                    return frame, None, kind
                case VarAssignExpr(d, exp):
                    frame = FrameDescriptor()
                    frame, frame_false = self.step_var_assign_exp(pair.leader().frame, d, exp)
                    return frame, frame_false, StepKind.INTERNAL
                case FieldAssignExpr(pfield, exp):
                    frame, frame2, kind = self.step_field_assign_exp(pair, pfield.ptr.name, pfield.name, exp)
                    return frame, frame2, kind
                case New(p):
                    frame, kind = self.step_new(pair, p.name)
                    return frame, None, kind
                case Free(p):
                    frame, kind = self.step_free(pair, p.name)
                    return frame, None, kind
                case Return(_):
                    frame = self.step_exit(pair.leader())
                    return frame, None, StepKind.INTERNAL
                case Skip():
                    frame = self.step_skip(pair.leader())
                    return frame, None, StepKind.INTERNAL
                case _:
                    raise NotImplementedError(f"Stepper.step not implemented for instruction: {inst}")
        except NonContinuosPairError:
            return None

    def psi_internal(self, sigma: Label, framed: FrameDescriptor) -> FrameDescriptor:
        for ptr_name in self.pointers():
            framed.upd[ptr_name] = False
        if self._replace_last_frame(sigma.frame):
            framed.index = sigma.frame.index
            assert framed.prev == sigma.frame.prev
        else:
            framed.index = sigma.frame.index + 1
            assert framed.prev == (Internal(), sigma.frame.index + 1)
        return framed

    def psi_external(self, pair: Pair, framed: FrameDescriptor) -> FrameDescriptor:
        sigma = pair.leader()
        tau = pair.follower()
        if tau.frame.index < 1:  # index <= 1:
            for ptr_name in self.pointers():
                framed.upd[ptr_name] = False
        else:
            a_ = next(f.index for f in reversed(sigma[1:]) if f.prev and f.prev[0] == pair.dir())
            for ptr_name in self.pointers():
                framed.upd[ptr_name] = not framed.isnil[ptr_name] and (
                    any(Here(ptr_name) in f.events for f in sigma[a_:]) or any(f.upd[ptr_name] for f in sigma[a_ + 1 :])
                )
        framed.index = tau.frame.index + 1
        assert framed.prev == (pair.rev_dir(), sigma.frame.index)
        return framed

    def _replace_last_frame(self, ancestor: Frame) -> bool:
        if ancestor.prev is None:
            return False
        if ancestor.prev[0] != Internal():
            return False
        return True

    def extend_pair_with_internal_frame(self, pair: Pair, framed: FrameDescriptor) -> Pair:
        ancestor_frame = pair.leader().frame
        if self._replace_last_frame(ancestor_frame):
            events: set[Event] = set(ancestor_frame.events)
            match framed.event:
                case FieldAssignP(pfield, p) if p is not None:
                    events = {
                        e
                        for e in events
                        if not (isinstance(e, FieldAssignP) or (isinstance(e, FieldAssignP) and e.p == pfield))
                    }
                case _:
                    pass
            if framed.event != NOP():
                events.add(framed.event)

            frame = Frame(
                index=ancestor_frame.index,
                active=cast(bool, framed.active),
                pc=framed.pc,
                isnil=frozendict(framed.isnil),
                upd=frozendict(framed.upd),
                events=frozenset(events),
                active_child=frozendict(framed.active_child),
                enum_vars=frozendict(framed.enum_values),
                enum_fields=frozendict(framed.enum_fields),
                prev=framed.prev,
            )
            new_leader = self.make_label(pair.leader().origin, frame)
            new_parent = new_leader if pair.leadership == LeadershipKind.PARENT else pair.follower()
            new_child = pair.follower() if pair.leadership == LeadershipKind.PARENT else new_leader
            new_pair = Pair(new_parent, new_child, pair.child_key, pair.leadership)
            return new_pair
        else:
            frame = Frame(
                index=ancestor_frame.index + 1,
                active=cast(bool, framed.active),
                pc=framed.pc,
                isnil=frozendict(framed.isnil),
                upd=frozendict(framed.upd),
                events=frozenset({framed.event}) if framed.event != NOP() else frozenset(),
                active_child=frozendict(framed.active_child),
                enum_vars=frozendict(framed.enum_values),
                enum_fields=frozendict(framed.enum_fields),
                prev=framed.prev,
            )
            new_leader = self.make_label(pair.leader(), frame)
            new_parent = new_leader if pair.leadership == LeadershipKind.PARENT else pair.follower()
            new_child = pair.follower() if pair.leadership == LeadershipKind.PARENT else new_leader
            new_pair = Pair(new_parent, new_child, pair.child_key, pair.leadership)
            return new_pair

    def extend_pair_with_external_frame(self, pair: Pair, framed: FrameDescriptor) -> Pair:
        frame = Frame(
            index=pair.follower().frame.index + 1,
            active=cast(bool, framed.active),
            pc=framed.pc,
            isnil=frozendict(framed.isnil),
            upd=frozendict(framed.upd),
            events=frozenset({framed.event}) if framed.event != NOP() else frozenset(),
            active_child=frozendict(framed.active_child),
            enum_vars=frozendict(framed.enum_values),
            enum_fields=frozendict(framed.enum_fields),
            prev=framed.prev,
        )
        new_follower = pair.leader()
        new_leader = self.make_label(pair.follower(), frame)
        new_leadership = pair.leadership.opposite()
        new_parent = new_leader if new_leadership == LeadershipKind.PARENT else new_follower
        new_child = new_follower if new_leadership == LeadershipKind.PARENT else new_leader
        new_pair = Pair(new_parent, new_child, pair.child_key, new_leadership)
        return new_pair

    @override
    def knit(self, pair: Pair) -> KnitResult:
        # special cases
        if pair.leader().frame.index == 0:
            return StepFailed()
        if any(e in {Exit(), ERR(), OOM(), LOF()} for e in pair.leader().frame.events):
            return StepFailed()

        step_result = self.step(pair)
        if step_result is None:
            return StepFailed()
        framed, framed2, kind = step_result
        if kind == StepKind.INTERNAL:
            if framed2 is None:
                framed = self.psi_internal(pair.leader(), framed)
                new_pair = self.extend_pair_with_internal_frame(pair, framed)
                return InternalStepResult((new_pair,))
            else:
                framed_true = framed
                framed_false = framed2
                framed_true = self.psi_internal(pair.leader(), framed_true)
                framed_false = self.psi_internal(pair.leader(), framed_false)
                new_pair_true = self.extend_pair_with_internal_frame(pair, framed_true)
                new_pair_false = self.extend_pair_with_internal_frame(pair, framed_false)
                return InternalStepResult((new_pair_true, new_pair_false))
        else:
            framed = self.psi_external(pair, framed)
            new_pair = self.extend_pair_with_external_frame(pair, framed)
            return ExternalStepResult(new_pair)
