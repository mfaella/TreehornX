"""Auxiliary predicates and functions of the Lab encoding (CAV25, Appendix C).

Positions inside a label are 1-based as in the paper: `sigma[i]` is the frame σ^i and
`sigma[len(sigma)]` is the top frame. The `prev` and `next` links of σ^i are stored in the frame
itself as directions only: the frames they link are found by `linked_frames`.
"""

from typing import Callable, Iterator

from treehornx.enum_models.core.Dir import Dir, Down, Up
from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Lab.Event import NOP, FieldAssignP, Here, Rewind
from treehornx.enum_models.Lab.Frame import Frame, MutableFrame

# ---------------------------------------------------------------------------
# Rewinding the lace (C.7)
# ---------------------------------------------------------------------------


def cur_rewind_pos(sigma: Lab, a: int) -> int:
    match sigma[a].event:
        case Rewind(b):
            return b
        case _:
            return a


def points_here(sigma: Lab, a: int, q: int) -> bool:
    """∨_{i∈[2,a]} (σ^i.event = ⟨q := here⟩ ∧ ∧_{j∈[i+1,a]} ¬σ^j.upd_q)"""
    for f in reversed(sigma[2:a]):
        if f.event == Here(q):
            return True
        if f.upd[q]:
            return False
    return False


def last_upd(sigma: Lab, a: int, q: int) -> int:
    return max((i for i, f in sigma.reversed_iter_indexed(2, a) if f.upd[q]), default=2)


def stop_rewind(sigma: Lab, a: int, q: int) -> bool:
    return not sigma[a].isnil[q] and points_here(sigma, cur_rewind_pos(sigma, a), q)


def stop_rewind2(sigma: Lab, a: int, q1: int, q2: int) -> bool:
    return stop_rewind(sigma, a, q1) or stop_rewind(sigma, a, q2)


def are_equal_after_rewind(sigma: Lab, a: int, p: int, q: int) -> bool:
    a_ = cur_rewind_pos(sigma, a)
    return points_here(sigma, a_, p) and points_here(sigma, a_, q)


def rewind_target(sigma: Lab, q: int) -> int | None:
    """a'' of rewind: the frame of σ where q was last updated, None when q is nil or points here."""
    a = len(sigma)
    if sigma[a].isnil[q]:
        return None
    a_ = cur_rewind_pos(sigma, a)
    if points_here(sigma, a_, q):
        return None
    return last_upd(sigma, a_, q)


def rewind2_target(sigma: Lab, q1: int, q2: int) -> int | None:
    """a'' of rewind2: the latest frame of σ where q1 or q2 was updated."""
    a = len(sigma)
    if sigma[a].isnil[q1] or sigma[a].isnil[q2]:
        return None
    a_ = cur_rewind_pos(sigma, a)
    if points_here(sigma, a_, q1) or points_here(sigma, a_, q2):
        return None
    return max(last_upd(sigma, a_, q1), last_upd(sigma, a_, q2))


def rewind_special_target(sigma: Lab, r: int, a_: int) -> int | None:
    """a'' of rewind_special: the frame of σ where r was last updated before (σ, a')."""
    if points_here(sigma, a_, r):
        return None
    return last_upd(sigma, a_, r)


# ---------------------------------------------------------------------------
# Links between the frames of a parent and its j-th child
# ---------------------------------------------------------------------------


def frames_with_next(label: Lab, d: Dir) -> list[int]:
    return [i for i, f in label.iter_indexed(1, len(label)) if f.next == d]


def frames_with_prev(label: Lab, d: Dir) -> list[int]:
    return [i for i, f in label.iter_indexed(1, len(label)) if f.prev == d]


def down_links(parent: Lab, child: Lab, j: int) -> Iterator[tuple[int, int]]:
    """Pairs (i, c) such that the lace steps from parent^i down to the frame child^c of its j-th child.

    The lace is a single path, so the k-th time it leaves the parent towards the j-th child it reaches the
    k-th frame of the child entered from above. A departure whose frame is not in the child yet has no link."""
    yield from zip(frames_with_next(parent, Down(j)), frames_with_prev(child, Up()))


def up_links(parent: Lab, child: Lab, j: int) -> Iterator[tuple[int, int]]:
    """Pairs (i, c) such that the lace steps from the frame child^c of the j-th child up to parent^i."""
    for c, i in zip(frames_with_next(child, Up()), frames_with_prev(parent, Down(j))):
        yield i, c


def linked_frames(parent: Lab, child: Lab, j: int) -> Iterator[tuple[int, int]]:
    """Pairs (i, c) such that the frame parent^i and the frame child^c of its j-th child are adjacent in the lace.

    The direction of a link is lost: a child frame entered from the parent and leaving to it is in two links,
    use `down_links` and `up_links` when the direction matters."""
    yield from down_links(parent, child, j)
    yield from up_links(parent, child, j)


# ---------------------------------------------------------------------------
# Value of a pointer field at (σ, a) (C.5)
# ---------------------------------------------------------------------------


def _is_pfield_assign(f: Frame, pfield: int) -> bool:
    """f.event = ⟨pfield := *⟩"""
    return isinstance(f.event, FieldAssignP) and f.event.pfield == pfield


def is_pfield_nil(sigma: Lab, a: int, pfield: int) -> bool:
    for f in reversed(sigma[2:a]):
        if _is_pfield_assign(f, pfield):
            return f.event == FieldAssignP(pfield, None)
    return False


def get_pfield_ptr(sigma: Lab, a: int, pfield: int) -> tuple[int, int] | None:
    """(r, i) such that the last assignment to pfield in σ^2..σ^a is ⟨pfield := r⟩ at position i."""
    for i, f in sigma.reversed_iter_indexed(2, a):
        match f.event:
            case FieldAssignP(pf, r) if pf == pfield:
                return None if r is None else (r, i)
            case _:
                pass
    return None


def is_pfield_implicit(sigma: Lab, a: int, pfield: int) -> bool:
    return not any(_is_pfield_assign(f, pfield) for f in reversed(sigma[2:a]))


def field_is_nil(sigma: Lab, a: int, pfield: int) -> bool:
    """pfield_nil(σ,a,pf) ∨ (pfield_implicit(σ,a,pf) ∧ ¬σ^a.active_child_pf): the field of the node
    holding σ^a is nil."""
    return is_pfield_nil(sigma, a, pfield) or (
        is_pfield_implicit(sigma, a, pfield) and not sigma[a].active_child[pfield]
    )


# ---------------------------------------------------------------------------
# Update flags (Psi_Up / Psi_Down)
# ---------------------------------------------------------------------------


def upd_since(sigma: Lab, a_: int, a: int, p: int) -> bool:
    """∨_{c∈[a',a]} σ^c.event = ⟨p := here⟩ ∨ ∨_{c∈[a'+1,a]} σ^c.upd_p"""
    return (
        any(f.event == Here(p) for f in reversed(sigma[a_:a])) or
        any(f.upd[p] for f in reversed(sigma[a_+1:a]))
    )


# ---------------------------------------------------------------------------
# Default values for a new frame (C.5)
# ---------------------------------------------------------------------------


def isnil_with(f1: Frame, p: int, value: bool) -> list[bool]:
    """f2.isnil_p = value ∧ ∧_{q∈PV\\{p}} f2.isnil_q = f1.isnil_q"""
    isnil = list(f1.isnil)
    isnil[p] = value
    return isnil


def default_active(fprev: Frame, fbelow: Frame, f: MutableFrame) -> None:
    f.active = fbelow.active


def default_isnil(fprev: Frame, fbelow: Frame, f: MutableFrame) -> None:
    f.isnil = list(fprev.isnil)


def default_event(fprev: Frame, fbelow: Frame, f: MutableFrame) -> None:
    f.event = NOP()


def default_pc(fprev: Frame, fbelow: Frame, f: MutableFrame) -> None:
    f.pc = fprev.pc


def default_active_child(fprev: Frame, fbelow: Frame, f: MutableFrame) -> None:
    """f.prev ≠ (j, *) → ∧_{i∈[k+m]} f.active_child_i = fbelow.active_child_i

    The case f.prev = (j, *) cannot be decided here: the prev link belongs to the label
    of f, which is created only after the frame is complete. A new frame has f.prev = (j, *)
    exactly when the lace steps up from the j-th child, so the remaining conjunct
    f.active_child_j = fprev.active is applied by `LabEngine.step_up_with_upd`, where it
    coincides with the synchronization f.active_child_j = τ^a.active required by Psi_Up.
    """
    f.active_child = list(fbelow.active_child)


_DEFAULTS: dict[str, Callable[[Frame, Frame, MutableFrame], None]] = {
    "active": default_active,
    "isnil": default_isnil,
    "event": default_event,
    "pc": default_pc,
    "active_child": default_active_child,
}


def default(*fields: str) -> Callable[[Frame, Frame, MutableFrame], MutableFrame]:
    """default_{fields}(fprev, fbelow, f): sets the given fields of f to their default value.

    `avail` is implicit (every frame of a label is unavailable), `upd` is set by the Psi
    predicates, and `val`/`d` are not part of the frame."""
    unknown = set(fields) - _DEFAULTS.keys()
    assert not unknown, f"Invalid default fields {unknown}. Valid fields are: {', '.join(_DEFAULTS)}"

    def _default(fprev: Frame, fbelow: Frame, f: MutableFrame) -> MutableFrame:
        for name in fields:
            _DEFAULTS[name](fprev, fbelow, f)
        return f

    return _default
