from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from loguru import logger

import treehornx.ir.expressions as ire
from treehornx.ir.function import Function
from treehornx.ir.instructions import *

from .core import *
from .core.dir import *
from .core.event import *
from .core.pair import LeadershipKind
from .helpers import *
from .ppexp import ppexp


class StepKind(Enum):
    INTERNAL = 1
    EXTERNAL = 2


class NonContinuosPairError(Exception):
    pass


@dataclass
class Stepper:
    function: Function
    k: int
    m: int
    n: int

    def pointers(self) -> Iterable[str]:
        for p in self.function.vars:
            if p.sort.is_ptr():
                yield p.name

    def rewind(self, pair: Pair, q: str) -> FrameBuilder:
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
        tau_b = FrameBuilder(tau.frame)
        tau_b.prev = (pair.rev_dir(), len(sigma) - 1)
        tau_b = default(sigma.frame, tau.frame, tau_b)
        tau_b.events.add(Rewind(b_))
        return tau_b

    def rewind2(self, pair: Pair, p: str, q: str) -> FrameBuilder:
        prewind = self.rewind(pair, p)
        qrewind = self.rewind(pair, q)
        assert any(isinstance(e, Rewind) for e in prewind.events)
        assert any(isinstance(e, Rewind) for e in qrewind.events)
        i = max(e.i for e in prewind.events if isinstance(e, Rewind))
        j = max(e.i for e in qrewind.events if isinstance(e, Rewind))
        prewind.events.add(Rewind(max(i, j)))
        return prewind

    def rewind_special(self, pair: Pair, r: str, a_: int) -> FrameBuilder:
        sigma = pair.leader()
        tau = pair.follower()
        a__ = last_upd(sigma, a_, r)
        dir, b_ = sigma[a__].prev  # type: ignore
        if dir != pair.dir():
            raise NonContinuosPairError()
        assert isinstance(b_, int)
        tau_b = FrameBuilder(tau.frame)
        tau_b.prev = (pair.rev_dir(), sigma.frame.index)
        tau_b = default(sigma.frame, tau.frame, tau_b)
        tau_b.events.add(Rewind2(b_, r))
        return tau_b

    def _set_prev_of_internal_step(self, f: FrameBuilder, fbelow: Frame) -> FrameBuilder:
        assert fbelow.prev is not None
        if fbelow.prev[0] == Internal():
            f.prev = fbelow.prev
        else:
            f.prev = (Internal(), fbelow.index)
        return f

    def error(self, sigma: Label) -> FrameBuilder:
        f1 = sigma.frame
        f2 = FrameBuilder(f1)
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        f2.events.add(ERR())
        return f2

    def oom(self, f1: Frame, f2: FrameBuilder) -> FrameBuilder:
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        f2.events.add(OOM())
        return f2

    def label_overflow(self, sigma: Label) -> FrameBuilder:
        f1 = sigma.frame
        f2 = FrameBuilder(f1)
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        f2.events.add(LOF())
        return f2

    def step_skip(self, sigma: Label) -> FrameBuilder:
        f1 = sigma.frame
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, int)
        f2 = FrameBuilder(f1)
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        f2.pc = next_pc
        return f2

    def step_assign_nil(self, sigma: Label, p: str) -> FrameBuilder:
        f1 = sigma.frame
        f2 = FrameBuilder(f1)
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        f2.isnil[p] = True
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, int)
        f2.pc = next_pc
        return f2

    def step_var_assign_exp(
        self, f1: Frame, f2: FrameBuilder, d: Var, exp: Expr
    ) -> tuple[FrameBuilder, FrameBuilder | None]:
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, int)
        f2.pc = next_pc
        exp = ppexp(exp, f1)
        if isinstance(exp, ire.EnumConst):
            assert isinstance(exp, ire.EnumConst)
            f2.enum_values[d.name] = exp.value
            return f2, None
        elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
            flag_name = f1.enum_values[exp.name]
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

    def step_new(self, pair: Pair, f__: FrameBuilder, p: str) -> tuple[FrameBuilder, StepKind]:
        f = pair.leader().frame
        f_ = pair.follower().frame
        # OOM
        if all(f.active_child[j] for j in range(self.k, self.k + self.m)):
            return self.oom(f, f__), StepKind.INTERNAL

        # normal case
        next_pc = self.function.info_at(f.pc).next_pc
        assert isinstance(next_pc, int)
        f__.pc = next_pc

        j = min(j for j in range(self.k, self.k + self.m) if not f.active_child[j])
        if pair.dir() != Down(j):
            raise NonContinuosPairError()
        f__.prev = (Up(), f.index)
        f__ = default(f, f_, f__)
        f__.isnil[p] = False
        f__.events.add(Here(p))
        f__.active = True
        f__.pc = next_pc
        return f__, StepKind.EXTERNAL

    def step_local_branch(self, sigma: Label) -> tuple[FrameBuilder | None, FrameBuilder | None]:
        f1 = sigma.frame
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, tuple)
        inst = self.function.instructions[f1.pc]
        assert isinstance(inst, IfGoto)
        expr = inst.condition
        expr = ppexp(expr, sigma.frame)
        ftrue, ffalse = None, None
        if expr == ire.TRUE or expr != ire.FALSE:
            ftrue = FrameBuilder(f1)
            ftrue = set_prev_of_internal_step(ftrue, f1)
            ftrue = default(f1, f1, ftrue)
            ftrue.pc = next_pc[0]
        if expr == ire.FALSE or expr != ire.TRUE:
            ffalse = FrameBuilder(f1)
            ffalse = set_prev_of_internal_step(ffalse, f1)
            ffalse = default(f1, f1, ffalse)
            ffalse.pc = next_pc[1]
        return ftrue, ffalse

    def step_assign_cond(self, sigma: Label, tau: Label, p: str, q: str) -> tuple[FrameBuilder, StepKind]:
        raise NotImplementedError("step_assign_cond not implemented yet")

    def step_ptr_assign_ptr(self, pair: Pair, p: str, q: str) -> tuple[FrameBuilder, StepKind]:
        # p = q
        sigma = pair.leader()
        if sigma.frame.isnil[q]:
            return self.step_assign_nil(sigma, p), StepKind.INTERNAL
        elif stop_rewind(sigma, q):
            sigma_a = FrameBuilder(sigma.frame)
            sigma_a = set_prev_of_internal_step(sigma_a, sigma.frame)
            sigma_a = set_ptr_here(sigma.frame, sigma_a, p)
            return sigma_a, StepKind.INTERNAL
        else:
            return self.rewind(pair, q), StepKind.EXTERNAL

    def step_field_assign_ptr(self, pair: Pair, p: str, q: str, pfield: str) -> tuple[FrameBuilder, StepKind]:
        """p->pfield := q"""
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma), StepKind.INTERNAL

        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, int)
            sigma_a = FrameBuilder(sigma.frame)
            sigma_a = set_prev_of_internal_step(sigma_a, sigma.frame)
            sigma_a = default(sigma.frame, sigma.frame, sigma_a)
            sigma_a.pc = next_pc
            events = set(e for e in sigma.frame.events if not isinstance(e, FieldAssignP) or e.pfield != pfield)
            events.add(FieldAssignP(pfield, None if sigma.frame.isnil[q] else q))
            sigma_a.events = events
            return sigma_a, StepKind.INTERNAL

        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_field_assign_exp(
        self, pair: Pair, p: str, pfield: str, exp: Expr
    ) -> tuple[FrameBuilder, FrameBuilder | None, StepKind]:
        """p->pfield := exp"""
        sigma = pair.leader()
        tau = pair.follower()
        if sigma.frame.isnil[p]:
            return self.error(sigma), None, StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, int)
            inst = self.function.instructions[sigma.frame.pc]
            assert isinstance(inst, FieldAssignExpr)
            exp = ppexp(exp, sigma.frame)
            tau_b = FrameBuilder(tau.frame)
            tau_b = set_prev_of_internal_step(tau_b, tau.frame)
            tau_b = default(sigma.frame, sigma.frame, tau_b)
            tau_b.pc = next_pc
            if isinstance(exp, ire.EnumConst):
                tau_b.enum_fields[pfield] = exp.value
            elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
                flag_name = sigma.frame.enum_fields[exp.name]
                tau_b.enum_fields[pfield] = flag_name
            elif sort_of(exp) == BOOL:
                tau_b_true = tau_b
                tau_b_false = deepcopy(tau_b)
                tau_b_true.enum_fields[pfield] = "TRUE"
                tau_b_false.enum_fields[pfield] = "FALSE"
                return tau_b_true, tau_b_false, StepKind.INTERNAL
            return tau_b, None, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), None, StepKind.EXTERNAL

    def step_var_assign_field(self, pair: Pair, var: str, p: str, pfield: str) -> tuple[FrameBuilder, StepKind]:
        """var := p->field"""
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma), StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, int)
            tau_b = FrameBuilder(sigma.frame)
            tau_b = set_prev_of_internal_step(tau_b, sigma.frame)
            tau_b = default(sigma.frame, sigma.frame, tau_b)
            tau_b.pc = next_pc
            if var in sigma.frame.enum_values:
                flag_name = sigma.frame.enum_fields[pfield]
                tau_b.enum_values[var] = flag_name
            return tau_b, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_free(self, pair: Pair, p: str) -> tuple[FrameBuilder, StepKind]:
        sigma = pair.leader()
        if sigma.frame.isnil[p]:
            return self.error(sigma), StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, int)
            tau_b = FrameBuilder(sigma.frame)
            tau_b = set_prev_of_internal_step(tau_b, sigma.frame)
            tau_b = default(sigma.frame, sigma.frame, tau_b)
            tau_b.pc = next_pc
            tau_b.active = False
            for q in self.pointers():
                if points_here(sigma, len(sigma) - 1, q):
                    tau_b.isnil[q] = True
                else:
                    tau_b.isnil[q] = sigma.frame.isnil[q]
            return tau_b, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_cmp_ptr(self, pair: Pair, p: str, q: str) -> tuple[FrameBuilder, StepKind]:
        sigma = pair.leader()
        isnil_p = sigma.frame.isnil[p]
        isnil_q = sigma.frame.isnil[q]
        if isnil_p or isnil_q:
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, tuple)
            ftrue = FrameBuilder(sigma.frame)
            ftrue = set_prev_of_internal_step(ftrue, sigma.frame)
            ftrue = default(sigma.frame, sigma.frame, ftrue)
            ftrue.pc = next_pc[0] if isnil_p == isnil_q else next_pc[1]
            return ftrue, StepKind.INTERNAL
        elif stop_rewind2(sigma, p, q):
            next_pc = self.function.info_at(sigma.frame.pc).next_pc
            assert isinstance(next_pc, tuple)
            frame = FrameBuilder(sigma.frame)
            frame = set_prev_of_internal_step(frame, sigma.frame)
            frame = default(sigma.frame, sigma.frame, frame)
            frame.pc = next_pc[0] if are_equal_after_rewind(sigma, p, q) else next_pc[1]
            return frame, StepKind.INTERNAL
        else:
            frame = self.rewind2(pair, p, q)
            return frame, StepKind.EXTERNAL

    def step_ptr_assign_field(self, pair: Pair, p: str, pfield: str, q: str) -> tuple[FrameBuilder, StepKind]:
        """p := q->pfield"""
        sigma = pair.leader()
        tau = pair.follower()
        if sigma.frame.isnil[q]:
            return self.error(sigma), StepKind.INTERNAL

        rewind2_event = next((e for e in sigma.frame.events if isinstance(e, Rewind2)), None)
        if rewind2_event is not None:
            i = rewind2_event.i
            r = rewind2_event.p
            if points_here(sigma, i, r):
                sigma_a = sigma.frame
                tau_b = FrameBuilder(sigma_a)
                return set_ptr_here(sigma_a, tau_b, p), StepKind.INTERNAL
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
                tau_b = FrameBuilder(tau.frame)
                tau_b.prev = (Up(), len(sigma) - 1)
                tau_b = default(sigma.frame, tau.frame, tau_b)
                tau_b.isnil[p] = False
                next_pc = self.function.info_at(sigma.frame.pc).next_pc
                assert isinstance(next_pc, int)
                tau_b.pc = next_pc
                tau_b.events.add(Here(p))
                return tau_b, StepKind.EXTERNAL
            else:
                for r in self.pointers():
                    for i in range(1, len(sigma)):
                        if not is_pfield_ptr(sigma, len(sigma) - 1, pfield, r, i):
                            continue
                        if points_here(sigma, i, r):
                            sigma_a = sigma.frame
                            tau_b = FrameBuilder(sigma_a)
                            return set_ptr_here(sigma_a, tau_b, p), StepKind.INTERNAL
                        else:
                            return self.rewind_special(pair, r, i), StepKind.EXTERNAL
                assert False, "Unreachable code in step_ptr_assign_field"
        else:
            return self.rewind(pair, q), StepKind.EXTERNAL

    def step_exit(self, sigma: Label) -> FrameBuilder:
        f1 = sigma.frame
        f2 = FrameBuilder(f1)
        f2 = set_prev_of_internal_step(f2, f1)
        f2 = default(f1, f1, f2)
        f2.events.add(Exit())
        return f2

    def step(self, pair: Pair) -> tuple[FrameBuilder, FrameBuilder | None, StepKind] | None:
        if pair.leader().id == 258 and pair.follower().id == 246 and pair.child_key == "next":
            pass
        try:
            pc = pair.leader().frame.pc
            if pc >= len(self.function.instructions):
                return self.step_exit(pair.leader()), None, StepKind.INTERNAL
            inst = self.function.instructions[pc]
            if len(pair.leader()) >= self.n:
                return self.label_overflow(pair.leader()), None, StepKind.INTERNAL
            logger.debug(f"step: {inst} (pc={pc})")
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
                    frame = FrameBuilder(pair.follower().frame)
                    frame, frame_false = self.step_var_assign_exp(pair.leader().frame, frame, d, exp)
                    return frame, frame_false, StepKind.INTERNAL
                case FieldAssignExpr(pfield, exp):
                    frame, frame2, kind = self.step_field_assign_exp(pair, pfield.ptr.name, pfield.name, exp)
                    return frame, frame2, kind
                case New(p):
                    frame, kind = self.step_new(pair, FrameBuilder(pair.follower().frame), p.name)
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
