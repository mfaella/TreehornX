from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import ir.expressions as ire
from chc.core import *
from chc.core.dir import *
from chc.core.event import *
from chc.core.pair import LeadershipKind
from ir.function import Function
from ir.instructions import *

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
        assert not sigma[-1].isnil[q]
        a_ = cur_rewind_pos(sigma)
        assert not points_here(sigma, a_, q)
        a__ = last_upd(sigma, a_, q)
        dir, b_ = sigma[a__].prev  # type: ignore
        if dir != pair.dir():
            raise NonContinuosPairError()
        assert isinstance(b_, int)
        tau_b = FrameBuilder(tau[-1])
        tau_b.prev = (pair.rev_dir(), len(sigma.frames) - 1)
        tau_b = default(sigma[-1], tau[-1], tau_b)
        tau_b.event = Rewind(b_)
        return tau_b

    def rewind2(self, pair: Pair, p: str, q: str) -> FrameBuilder:
        prewind = self.rewind(pair, p)
        qrewind = self.rewind(pair, q)
        assert isinstance(prewind.event, Rewind)
        assert isinstance(qrewind.event, Rewind)
        i = max(prewind.event.i, qrewind.event.i)
        prewind.event = Rewind(i)
        return prewind

    def rewind_special(self, pair: Pair, r: str, i: int) -> FrameBuilder:
        sigma = pair.leader()
        tau = pair.follower()
        a__ = last_upd(sigma, i, r)
        dir, b_ = sigma[a__].prev  # type: ignore
        if dir != pair.dir():
            raise NonContinuosPairError()
        assert isinstance(b_, int)
        tau_b = FrameBuilder(tau[-1])
        tau_b.prev = (pair.rev_dir(), sigma[-1].index)
        tau_b = default(sigma[-1], tau[-1], tau_b)
        tau_b.event = Rewind2(b_, r)
        return tau_b

    def error(self, sigma: Label) -> FrameBuilder:
        f1 = sigma[-1]
        f2 = FrameBuilder(f1)
        f2.prev = (Internal(), len(sigma.frames) - 1)
        f2 = default(f1, f1, f2)
        f2.event = ERR()
        return f2

    def oom(self, f1: Frame, f2: FrameBuilder) -> FrameBuilder:
        f2 = default(f1, f1, f2)
        f2.event = OOM()
        f2.prev = (Internal(), f1.index)
        return f2

    def label_overflow(self, sigma: Label) -> FrameBuilder:
        f1 = sigma[-1]
        f2 = FrameBuilder(f1)
        f2.prev = (Internal(), len(sigma.frames) - 1)
        f2 = default(f1, f1, f2)
        f2.event = LOF()
        return f2

    def step_skip(self, sigma: Label) -> FrameBuilder:
        f1 = sigma.frames[-1]
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, int)
        f2 = FrameBuilder(f1)
        f2.prev = (Internal(), len(sigma.frames) - 1)
        f2 = default(f1, f1, f2)
        f2.pc = next_pc
        return f2

    def step_assign_nil(self, sigma: Label, p: str) -> FrameBuilder:
        f1 = sigma.frames[-1]
        f2 = FrameBuilder(f1)
        f2.prev = (Internal(), len(sigma.frames) - 1)
        f2 = default(f1, f1, f2)
        f2.isnil[p] = True
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, int)
        f2.pc = next_pc
        return f2

    def step_var_assign_exp(
        self, f1: Frame, f2: FrameBuilder, d: Var, exp: Expr
    ) -> tuple[FrameBuilder, FrameBuilder | None]:
        f2 = default(f1, f1, f2)
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, int)
        f2.pc = next_pc
        if isinstance(exp, ire.EnumConst):
            assert isinstance(exp, ire.EnumConst)
            f2.enum_values[d.name] = exp.value
            return f2, None
        elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
            flag_name = f1.enum_values[exp.name]
            f2.enum_values[d.name] = flag_name
            return f2, None
        elif sort_of(d) is BOOL:
            f2_true = f2
            f2_false = deepcopy(f2)
            f2_true.enum_values[d.name] = "TRUE"
            f2_false.enum_values[d.name] = "FALSE"
            return f2_true, f2_false
        else:
            return f2, None

    def step_new(self, pair: Pair, f__: FrameBuilder, p: str) -> tuple[FrameBuilder, StepKind]:
        f = pair.leader()[-1]
        f_ = pair.follower()[-1]
        # OOM
        if all(f.active_child[j] for j in range(self.k, self.k + self.m)):
            return self.oom(f, f__), StepKind.INTERNAL

        # normal case
        next_pc = self.function.info_at(f.pc).next_pc
        assert isinstance(next_pc, int)
        f__.pc = next_pc

        j = min(filter(lambda j: not f.active_child[j], range(self.k, self.k + self.m)))
        if j == pair.child_key:
            raise NonContinuosPairError()
        f__.prev = (Down(j), f.index)
        f__ = default(f, f_, f__)
        f__.isnil[p] = False
        f__.event = Here(p)
        f__.pc = next_pc
        return f__, StepKind.EXTERNAL

    def step_local_branch(self, sigma: Label) -> tuple[FrameBuilder | None, FrameBuilder | None]:
        f1 = sigma[-1]
        next_pc = self.function.info_at(f1.pc).next_pc
        assert isinstance(next_pc, tuple)
        inst = self.function.instructions[f1.pc]
        assert isinstance(inst, IfGoto)
        expr = inst.condition
        expr = ppexp(expr, sigma)
        ftrue, ffalse = None, None
        if expr == ire.TRUE or expr != ire.FALSE:
            ftrue = FrameBuilder(f1)
            ftrue.prev = (Internal(), len(sigma.frames) - 1)
            ftrue = default(f1, f1, ftrue)
            ftrue.pc = next_pc[0]
        if expr == ire.FALSE or expr != ire.TRUE:
            ffalse = FrameBuilder(f1)
            ffalse.prev = (Internal(), len(sigma.frames) - 1)
            ffalse = default(f1, f1, ffalse)
            ffalse.pc = next_pc[1]
        return ftrue, ffalse

    def step_assign_cond(self, sigma: Label, tau: Label, p: str, q: str) -> tuple[FrameBuilder, StepKind]:
        raise NotImplementedError("step_assign_cond not implemented yet")

    def step_assign_ptr(self, pair: Pair, p: str, q: str) -> tuple[FrameBuilder, StepKind]:
        sigma = pair.leader()
        if sigma[-1].isnil[q]:
            return self.step_assign_nil(sigma, p), StepKind.INTERNAL
        elif stop_rewind(sigma, q):
            sigma_a = FrameBuilder(sigma[-1])
            sigma_a.prev = (Internal(), len(sigma.frames) - 1)
            sigma_a = set_ptr_here(sigma[-1], sigma_a, p)
            return sigma_a, StepKind.INTERNAL
        else:
            return self.rewind(pair, q), StepKind.EXTERNAL

    def step_field_assign_ptr(self, pair: Pair, p: str, q: str, pfield: str) -> tuple[FrameBuilder, StepKind]:
        """p->pfield := q"""
        sigma = pair.leader()
        if sigma[-1].isnil[p]:
            return self.error(sigma), StepKind.INTERNAL

        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma[-1].pc).next_pc
            assert isinstance(next_pc, int)
            sigma_a = FrameBuilder(sigma[-1])
            sigma_a.prev = (Internal(), len(sigma.frames) - 1)
            sigma_a = default(sigma[-1], sigma[-1], sigma_a)
            sigma_a.pc = next_pc
            sigma_a.event = FieldAssignP(pfield, None if sigma[-1].isnil[q] else q)
            return sigma_a, StepKind.INTERNAL

        else:
            return self.rewind(pair, q), StepKind.EXTERNAL

    def step_field_assign_exp(
        self, pair: Pair, p: str, pfield: str, exp: Expr
    ) -> tuple[FrameBuilder, FrameBuilder | None, StepKind]:
        """p->pfield := exp"""
        sigma = pair.leader()
        tau = pair.follower()
        if sigma[-1].isnil[p]:
            return self.error(sigma), None, StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma[-1].pc).next_pc
            assert isinstance(next_pc, int)
            inst = self.function.instructions[sigma[-1].pc]
            assert isinstance(inst, FieldAssignExpr)
            exp = ppexp(exp, sigma)
            tau_b = FrameBuilder(tau[-1])
            tau_b.prev = (Internal(), len(sigma.frames) - 1)
            tau_b = default(sigma[-1], tau[-1], tau_b)
            tau_b.pc = next_pc
            if isinstance(exp, ire.EnumConst):
                tau_b.enum_fields[pfield] = exp.value
            elif isinstance(exp, ire.Var) and sort_of(exp).is_enum():
                flag_name = sigma[-1].enum_fields[exp.name]
                tau_b.enum_fields[pfield] = flag_name
            elif sort_of(exp) is BOOL:
                tau_b_true = tau_b
                tau_b_false = deepcopy(tau_b)
                tau_b_true.enum_fields[pfield] = "TRUE"
                tau_b_false.enum_fields[pfield] = "FALSE"
                return tau_b_true, tau_b_false, StepKind.INTERNAL
            return tau_b, None, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), None, StepKind.EXTERNAL

    def step_var_assign_field(self, pair: Pair, var: str, p: str, pfield: str) -> tuple[FrameBuilder, StepKind]:
        """var := p->pfield"""
        sigma = pair.leader()
        if sigma[-1].isnil[p]:
            return self.error(sigma), StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma[-1].pc).next_pc
            assert isinstance(next_pc, int)
            tau_b = FrameBuilder(sigma[-1])
            tau_b.prev = (Internal(), len(sigma.frames) - 1)
            tau_b = default(sigma[-1], sigma[-1], tau_b)
            tau_b.pc = next_pc
            if var in sigma[-1].enum_values:
                flag_name = sigma[-1].enum_fields[pfield]
                tau_b.enum_values[var] = flag_name
            return tau_b, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_free(self, pair: Pair, p: str) -> tuple[FrameBuilder, StepKind]:
        sigma = pair.leader()
        if sigma[-1].isnil[p]:
            return self.error(sigma), StepKind.INTERNAL
        elif stop_rewind(sigma, p):
            next_pc = self.function.info_at(sigma[-1].pc).next_pc
            assert isinstance(next_pc, int)
            tau_b = FrameBuilder(sigma[-1])
            tau_b.prev = (Internal(), len(sigma.frames) - 1)
            tau_b = default(sigma[-1], sigma[-1], tau_b)
            tau_b.pc = next_pc
            for q in self.pointers():
                if points_here(sigma, len(sigma.frames) - 1, q):
                    tau_b.isnil[q] = True
                else:
                    tau_b.isnil[q] = sigma[-1].isnil[q]
            return tau_b, StepKind.INTERNAL
        else:
            return self.rewind(pair, p), StepKind.EXTERNAL

    def step_cmp_ptr(self, sigma: Label, tau: Label, p: str, q: str, dest: str) -> tuple[FrameBuilder, StepKind]:
        raise NotImplementedError("step_cmp_ptr not implemented yet")

    def step_ptr_assign_field(self, pair: Pair, p: str, pfield: str, q: str) -> tuple[FrameBuilder, StepKind]:
        """p := q->field"""
        sigma = pair.leader()
        tau = pair.follower()
        if sigma[-1].isnil[p]:
            return self.error(sigma), StepKind.INTERNAL

        match sigma[-1].event:
            case Rewind2(_, r) if points_here(sigma, len(sigma), r):
                sigma_a = sigma[-1]
                tau_b = FrameBuilder(sigma_a)
                return set_ptr_here(sigma_a, tau_b, p), StepKind.INTERNAL
            case Rewind2(i, r):
                return self.rewind_special(pair, r, i), StepKind.EXTERNAL
            case _ if stop_rewind(sigma, q):
                if is_pfield_nil(sigma, pfield) or (
                    is_pfield_implicit(sigma, pfield) and not sigma[-1].active_child[pfield]
                ):
                    return self.step_assign_nil(sigma, p), StepKind.INTERNAL
                elif is_pfield_implicit(sigma, pfield) and sigma[-1].active_child[pfield]:
                    tau_b = FrameBuilder(tau[-1])
                    tau_b = default(sigma[-1], tau[-1], tau_b)
                    next_pc = self.function.info_at(sigma[-1].pc).next_pc
                    assert isinstance(next_pc, int)
                    tau_b.pc = next_pc
                    tau_b.event = Here(p)
                    return tau_b, StepKind.INTERNAL
            case _:
                for r in self.pointers():
                    for i in range(1, len(sigma)):
                        if not is_pfield_ptr(sigma, len(sigma), pfield, r, i):
                            continue
                        if points_here(sigma, i, r):
                            sigma_a = sigma[-1]
                            tau_b = FrameBuilder(sigma_a)
                            return set_ptr_here(sigma_a, tau_b, p), StepKind.INTERNAL
                        else:
                            return self.rewind_special(pair, r, i), StepKind.EXTERNAL
        raise RuntimeError("Unreachable code in step_ptr_assign_field")

    def step_exit(self, sigma: Label) -> FrameBuilder:
        f1 = sigma[-1]
        f2 = FrameBuilder(f1)
        f2.prev = (Internal(), len(sigma.frames) - 1)
        f2 = default(f1, f1, f2)
        f2.event = Exit()
        return f2

    def step(self, pair: Pair) -> tuple[FrameBuilder, FrameBuilder | None, StepKind] | None:
        try:
            pc = pair.leader()[-1].pc
            inst = self.function.instructions[pc]
            if len(pair.leader()) >= self.k + self.m:
                return self.label_overflow(pair.leader()), None, StepKind.INTERNAL
            match inst:
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
                    frame.pc = self.function.info_at(pc).next_pc  # type: ignore
                    return frame, None, StepKind.INTERNAL
                case PtrAssignNil(p):
                    frame = self.step_assign_nil(pair.leader(), p.name)
                    return frame, None, StepKind.INTERNAL
                case PtrAssignPtr(p, q):
                    frame, kind = self.step_assign_ptr(pair, p.name, q.name)
                    return frame, None, kind
                case PtrAssignField(p, qfield):
                    frame, kind = self.step_ptr_assign_field(pair, p.name, qfield.name, qfield.ptr.name)
                    return frame, None, kind
                case FieldAssignPtr(pfield, q):
                    frame, kind = self.step_field_assign_ptr(pair, pfield.ptr.name, q.name, pfield.name)
                    return frame, None, kind
                case VarAssignExpr(d, exp):
                    frame = FrameBuilder(pair.follower()[-1])
                    frame = self.step_var_assign_exp(pair.leader()[-1], frame, d, exp)
                    return frame, None, StepKind.INTERNAL
                case FieldAssignExpr(pfield, exp):
                    frame, frame2, kind = self.step_field_assign_exp(pair, pfield.ptr.name, pfield.name, exp)
                    return frame, frame2, kind
                case New(p):
                    frame, kind = self.step_new(pair, FrameBuilder(pair.follower()[-1]), p.name)
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
