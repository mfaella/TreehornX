from typing import Callable

from treehornx.enum_labels.core.Dir import Down
from treehornx.enum_labels.core.Event import NOP, FieldAssignP, FieldHere, Here, Rewind
from treehornx.enum_labels.core.Frame import Frame, FrameDescriptor
from treehornx.enum_labels.core.Label import Label


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
