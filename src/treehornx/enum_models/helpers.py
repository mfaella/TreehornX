"""Auxiliary predicates and functions of the Lab encoding (CAV25, Appendix C).

Positions inside a label are 1-based as in the paper: `sigma[i]` is the frame σ^i and
`sigma[len(sigma)]` is the top frame. The `prev` and `next` links of σ^i are stored in the frame
itself as directions only: the frames they link are found by `linked_frames`.
"""

from typing import Callable, Iterable, Iterator


from treehornx.enum_models.enviroment import Env, global_env
from treehornx.enum_models.labels import ERR, NOP, OOM, Dir, Down, ExitCode, FieldAssignP, Frame, Here, MutableFrame, Rewind, TLab, Up
from treehornx.enum_models.labels import Lab
from treehornx import ir
from treehornx.enum_models.tainting import BoolPlus, TaintPtrCoord


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


def lab_down_links(parent: Lab, child: Lab, j: int) -> Iterator[tuple[int, int]]:
    """Pairs (i, c) such that the lace steps from parent^i down to the frame child^c of its j-th child.

    The lace is a single path, so the k-th time it leaves the parent towards the j-th child it reaches the
    k-th frame of the child entered from above. A departure whose frame is not in the child yet has no link."""
    yield from zip(frames_with_next(parent, Down(j)), frames_with_prev(child, Up()))


def lab_up_links(parent: Lab, child: Lab, j: int) -> Iterator[tuple[int, int]]:
    """Pairs (i, c) such that the lace steps from the frame child^c of the j-th child up to parent^i."""
    for c, i in zip(frames_with_next(child, Up()), frames_with_prev(parent, Down(j))):
        yield i, c


def linked_frames(parent: Lab, child: Lab, j: int) -> Iterator[tuple[int, int]]:
    """Pairs (i, c) such that the frame parent^i and the frame child^c of its j-th child are adjacent in the lace.

    The direction of a link is lost: a child frame entered from the parent and leaving to it is in two links,
    use `down_links` and `up_links` when the direction matters."""
    yield from lab_down_links(parent, child, j)
    yield from lab_up_links(parent, child, j)


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
    return any(f.event == Here(p) for f in reversed(sigma[a_:a])) or any(f.upd[p] for f in reversed(sigma[a_ + 1 : a]))


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


# ---------------------------------------------------------------------------
# Lab Query CAV25
# ---------------------------------------------------------------------------


def label_exit(label: Lab, e: Env = global_env()) -> ExitCode:
    match label.frame.event:
        case ERR():
            return ExitCode.E
        case OOM():
            return ExitCode.M
        case _ if isinstance(e.func[label.frame.pc], ir.Exit):
            return ExitCode.C
        case _ if len(label) > e.n:
            return ExitCode.O
        case _:
            return ExitCode.N

# ---------------------------------------------------------------------------
# tainting (POPL27, Fig. 8 and Appendix C)
# ---------------------------------------------------------------------------

def end_of_lace(label: Lab, e: Env = global_env()) -> bool:
    return label_exit(label, e) != ExitCode.N


def trail_origin(sigma: Lab, i2: int, p: int) -> tuple[int, Dir] | None:
    """Where the trail of p at (σ, i2) leaves σ, going backward along the lace like the rewind of CAV25.

    None when p points to the node of σ (the trail ends here) or when it does not leave σ through an
    external link; otherwise (i_upd, dir), with i_upd = last_upd(σ, i2, p) and dir = σ^{i_upd}.prev."""
    if points_here(sigma, i2, p):
        return None
    i_upd = last_upd(sigma, i2, p)
    prev = sigma[i_upd].prev
    if not isinstance(prev, (Up, Down)):
        return None
    return i_upd, prev


def trail_up(parent: TLab, child: TLab, j: int) -> Iterator[tuple[TaintPtrCoord, TaintPtrCoord, BoolPlus]]:
    """The trails of the j-th child continuing on the parent: the key in the child, the key they reach in the
    parent and their value."""
    sigma, tau, = parent.lab, child.lab
    for (p, c), v in child.taint_ptr.items():
        origin = trail_origin(tau, c, p)
        if origin is None or origin[1] != Up():
            continue
        i1 = next((i for i, c_ in lab_down_links(sigma, tau, j) if c_ == origin[0]), None)
        if i1 is not None:
            yield (p, c), (p, i1), v


def trail_down(parent: TLab, child: TLab, j: int) -> Iterator[tuple[TaintPtrCoord, TaintPtrCoord, BoolPlus]]:
    """The trails of the parent continuing on its j-th child: the key in the parent, the key they reach in the
    child and their value."""
    sigma, tau = parent.lab, child.lab
    for (p, i2), v in parent.taint_ptr.items():
        origin = trail_origin(sigma, i2, p)
        if origin is None or origin[1] != Down(j):
            continue
        b = next((c for i, c in lab_up_links(sigma, tau, j) if i == origin[0]), None)
        if b is not None:
            yield (p, i2), (p, b), v


def field_trails(sigma: Lab, fields: Iterable[int]) -> Iterable[tuple[int, int]]:
    """(p, i) for every pointer field pf among `fields` whose final value is the target of p:
    child_is_ptr(σ, pf, p, i)."""
    for pfield in fields:
        ptr = get_pfield_ptr(sigma, len(sigma), pfield)
        if ptr is not None:
            yield ptr


def child_is_struct(sigma: Lab, j: int, k: int) -> bool:
    """child_is_struct(σ, j): at the end, the j-th pointer field of the node still holds its input child, which
    exists."""
    return j < k and is_pfield_implicit(sigma, len(sigma), j) and sigma[1].active_child[j]
