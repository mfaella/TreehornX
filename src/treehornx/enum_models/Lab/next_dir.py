"""Direction in which the lace leaves a new frame (its `next` link).

A label either steps internally or sends the lace out, never both, so the direction of the step leaving the
top frame is decided by the frame and its label alone: the cases mirror the dispatch of `LabEngine.step_int_frames`
and `LabEngine.step_ext`, the rewinding ones go back where the pointer was last updated.
"""

from treehornx import ir
from treehornx.enum_models.core.Dir import Dir, Down, Internal
from treehornx.enum_models.Lab.Event import ERR, OOM, RwdSpec
from treehornx.enum_models.Lab.Frame import MutableFrame
from treehornx.enum_models.Lab.helpers import (
    field_is_nil,
    get_pfield_ptr,
    is_pfield_implicit,
    points_here,
    rewind2_target,
    rewind_special_target,
    rewind_target,
    stop_rewind,
    stop_rewind2,
)
from treehornx.enum_models.Lab.Lab import Lab


def rewind_dir(sigma: Lab, a__: int | None) -> Dir | None:
    """σ^{a''}.prev, the direction the lace rewinds to, None when there is no external frame to rewind to."""
    if a__ is None:
        return None
    match sigma[a__].prev:
        case Internal() | None:
            return None
        case d:
            return d


def _on_ptr(sigma: Lab, p: int) -> Dir | None:
    """Instructions dereferencing p: an error if p is nil, local if p points here, otherwise rewind to p."""
    if sigma.frame.isnil[p] or stop_rewind(sigma, len(sigma), p):
        return Internal()
    return rewind_dir(sigma, rewind_target(sigma, p))


def _cmp_ptr(sigma: Lab, p: int, q: int) -> Dir | None:
    f = sigma.frame
    if f.isnil[p] or f.isnil[q] or stop_rewind2(sigma, len(sigma), p, q):
        return Internal()
    return rewind_dir(sigma, rewind2_target(sigma, p, q))


def _load_ptr_field(sigma: Lab, q: int, pfield: int) -> Dir | None:
    """p := q -> pfield, see LabEngine.step_assgn_from_field_{int,ext,down}."""
    f, a = sigma.frame, len(sigma)
    if f.isnil[q]:
        return Internal()
    match f.event:
        case RwdSpec(i, r):
            if points_here(sigma, i, r):
                return Internal()
            return rewind_dir(sigma, rewind_special_target(sigma, r, i))
        case _ if not stop_rewind(sigma, a, q):
            return rewind_dir(sigma, rewind_target(sigma, q))
        case _:
            if field_is_nil(sigma, a, pfield):
                return Internal()
            ptr = get_pfield_ptr(sigma, a, pfield)
            if ptr is not None:
                r, i = ptr
                if points_here(sigma, i, r):
                    return Internal()
                return rewind_dir(sigma, rewind_special_target(sigma, r, i))
            if is_pfield_implicit(sigma, a, pfield) and f.active_child[pfield]:
                return Down(pfield)
            return None


def predict_next_dir(function: ir.Function, m: int, n: int, label: Lab, f: MutableFrame) -> Dir | None:
    """Direction of the step leaving `f` once appended to `label`, None if the lace ends at `f` or is stuck.

    Every field of `f` but `next` must be set."""
    sigma = Lab(f.to_frozen(), label)
    frame = sigma.frame
    if isinstance(frame.event, (ERR, OOM)) or isinstance(function[frame.pc], ir.Exit) or len(sigma) > n:
        return None
    k = function.node.k
    match function[frame.pc]:
        case (
            ir.Goto()
            | ir.AssignData()
            | ir.AssignCond(_, ir.IsNil())
            | ir.AssignNil()
            | ir.IfGoto(ir.IsNil())
            | ir.IfGoto(ir.DataCond())
        ):
            return Internal()
        case ir.AssignCond(_, ir.PtrEq(p, q)) | ir.IfGoto(ir.PtrEq(p, q, _)):
            return _cmp_ptr(sigma, p, q)
        case ir.AssignPtr(_, q):
            return _on_ptr(sigma, q)
        case ir.LoadPtrField(_, q, pfield):
            return _load_ptr_field(sigma, q, pfield)
        case (
            ir.AssignCond(_, ir.FieldIsNil(p, _, _))
            | ir.IfGoto(ir.FieldIsNil(p, _, _))
            | ir.StoreNilField(p, _)
            | ir.StorePtrField(p, _, _)
            | ir.StoreDataField(p, _, _)
            | ir.LoadDataField(_, p, _)
            | ir.Free(p)
        ):
            return _on_ptr(sigma, p)
        case ir.New(_):
            j = next((j for j in range(k, k + m) if not frame.active_child[j]), None)
            return Internal() if j is None else Down(j)
        case stmt:
            raise NotImplementedError(f"next direction not implemented for statement: {stmt}")
