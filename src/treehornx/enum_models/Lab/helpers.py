"""Auxiliary predicates and functions of the Lab encoding (CAV25, Appendix C).

Positions inside a label are 1-based as in the paper: `sigma[i]` is the frame σ^i and
`sigma[len(sigma)]` is the top frame. The `prev`/`next` links of σ^i are stored on the
prefix of `sigma` of length i (see `prev_of`/`next_of`).
"""

from typing import Callable

from treehornx.enum_models.core.Dir import Dir
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.Lab.Event import NOP, FieldAssignP, Here, Rewind
from treehornx.enum_models.Lab.Frame import Frame, MutableFrame

# ---------------------------------------------------------------------------
# Lace links
# ---------------------------------------------------------------------------


def prev_of(sigma: Label[Frame], i: int) -> tuple[Dir, int] | None:
    """σ^i.prev"""
    return sigma.cut(i).prev


def next_of(sigma: Label[Frame], i: int) -> tuple[Dir, int] | None:
    """σ^i.next"""
    return sigma.cut(i).next


def last_visit(tau: Label[Frame], dir: Dir, j: int) -> int | None:
    """max{i ∈ [n] | τ^i.next = (dir, c), c ≤ j}, None when the set is empty."""
    visits = [
        i for i in range(1, len(tau) + 1)
        if (nxt := next_of(tau, i)) is not None and nxt[0] == dir and nxt[1] <= j
    ]
    return max(visits, default=None)


# ---------------------------------------------------------------------------
# Rewinding the lace (C.7)
# ---------------------------------------------------------------------------


def cur_rewind_pos(sigma: Label[Frame], a: int) -> int:
    match sigma[a].event:
        case Rewind(b):
            return b
        case _:
            return a


def points_here(sigma: Label[Frame], a: int, q: int) -> bool:
    """∨_{i∈[2,a]} (σ^i.event = ⟨q := here⟩ ∧ ∧_{j∈[i+1,a]} ¬σ^j.upd_q)"""
    for f in reversed(sigma[2 : a + 1]):
        if f.event == Here(q):
            return True
        if f.upd[q]:
            return False
    return False


def last_upd(sigma: Label[Frame], a: int, q: int) -> int:
    return max((i for i in range(2, a + 1) if sigma[i].upd[q]), default=2)


def stop_rewind(sigma: Label[Frame], a: int, q: int) -> bool:
    return not sigma[a].isnil[q] and points_here(sigma, cur_rewind_pos(sigma, a), q)


def stop_rewind2(sigma: Label[Frame], a: int, q1: int, q2: int) -> bool:
    return stop_rewind(sigma, a, q1) or stop_rewind(sigma, a, q2)


def are_equal_after_rewind(sigma: Label[Frame], a: int, p: int, q: int) -> bool:
    a_ = cur_rewind_pos(sigma, a)
    return points_here(sigma, a_, p) and points_here(sigma, a_, q)


# ---------------------------------------------------------------------------
# Value of a pointer field at (σ, a) (C.5)
# ---------------------------------------------------------------------------


def _is_pfield_assign(f: Frame, pfield: int) -> bool:
    """f.event = ⟨pfield := *⟩"""
    return isinstance(f.event, FieldAssignP) and f.event.pfield == pfield


def is_pfield_nil(sigma: Label[Frame], a: int, pfield: int) -> bool:
    for f in reversed(sigma[2 : a + 1]):
        if _is_pfield_assign(f, pfield):
            return f.event == FieldAssignP(pfield, None)
    return False


def is_pfield_ptr(sigma: Label[Frame], a: int, pfield: int, r: int, i: int) -> bool:
    return (
        2 <= i <= a
        and sigma[i].event == FieldAssignP(pfield, r)
        and not any(_is_pfield_assign(f, pfield) for f in sigma[i + 1 : a + 1])
    )


def is_pfield_implicit(sigma: Label[Frame], a: int, pfield: int) -> bool:
    return not any(_is_pfield_assign(f, pfield) for f in sigma[2 : a + 1])


# ---------------------------------------------------------------------------
# Update flags (Psi_Up / Psi_Down)
# ---------------------------------------------------------------------------


def upd_since(sigma: Label[Frame], a_: int, a: int, p: int) -> bool:
    """∨_{c∈[a',a]} σ^c.event = ⟨p := here⟩ ∨ ∨_{c∈[a'+1,a]} σ^c.upd_p"""
    return any(f.event == Here(p) for f in sigma[a_ : a + 1]) or any(f.upd[p] for f in sigma[a_ + 1 : a + 1])


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
