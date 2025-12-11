from itertools import islice

from chc.core import Label, Frame, FrameBuilder
from chc.core.event import *
from chc.core.dir import Down, Internal


def is_pfield_nil(sigma: Label, pfield: str) -> bool:
    for f in reversed(sigma.frames[1:]):
        match f.event:
            case FieldAssignP(pf, p) if pf == pfield:
                return p is None
            case _:
                continue

    return False


def is_pfield_ptr(sigma: Label, a: int, pfield: str, r: str, i: int) -> bool:
    for f in reversed(sigma.frames[i + 1 : a + 1]):
        match f.event:
            case FieldAssignP(pf, _) if pf == pfield:
                return False
            case _:
                continue

    return sigma.frames[i].event == FieldAssignP(pfield, r)


def is_pfield_implicit(sigma: Label, pfield: str) -> bool:
    for f in reversed(sigma.frames[1:]):
        match f.event:
            case FieldAssignP(pf, p) if pf == pfield:
                return False
            case _:
                continue

    return True


def cur_rewind_pos(sigma: Label) -> int:
    match sigma.frames[-1].event:
        case Rewind(b):
            return b
        case _:
            return len(sigma.frames) - 1


def points_here(sigma: Label, a: int, q: str) -> bool:
    for f in reversed(sigma.frames[1:a]):
        match f.event:
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
    upd_q_indices = {index for index ,f in enumerate(sigma.frames[1 : a + 1], start=1) if f.upd[q]}
    return max(upd_q_indices) if upd_q_indices else 1


def stop_rewind(sigma: Label, q: str) -> bool:
    a_ = cur_rewind_pos(sigma)
    return not sigma[-1].upd[q] and points_here(sigma, a_, q)


def stop_rewind2(sigma: Label, q1: str, q2: str) -> bool:
    return stop_rewind(sigma, q1) and stop_rewind(sigma, q2)


def default_active_child(fprev: Frame, fbelow: Frame, f: FrameBuilder) -> FrameBuilder:
    assert f.prev is not None
    match f.prev:
        case Down(j), _:
            f.active_child[j] = fprev.active
            for i in filter(lambda i: i != j, fbelow.active_child.keys())
                f.active_child[i] = fbelow.active_child[i]
        case _:
            f.active_child = dict(fbelow.active_child)
    return f

def default(fprev: Frame, fbelow: Frame, f: FrameBuilder) -> FrameBuilder:
    """Create a default frame based on the previous frame and the frame below. It set to default all the fields."""
    f.active = fbelow.active
    f.enum_values = dict(fprev.enum_values)
    f.enum_fields = dict(fbelow.enum_fields)
    f.isnil = dict(fprev.isnil)
    f.event = NOP()
    f.pc = fprev.pc
    f = default_active_child(fprev, fbelow, f)
    return f


def set_ptr_here(f1: Frame, f2: FrameBuilder, p: str) -> FrameBuilder:
    f2.prev = (Internal(), f1.index)
    f2 = default(f1, f1, f2)
    f2.pc = f1.pc + 1
    f2.event = Here(p)
    f2.isnil[p] = False
    return f2
