"""Auxiliary predicates of the tainting (POPL27, Fig. 8 and Appendix C).

Positions inside a label are 1-based, as in `Lab/helpers.py`.
"""

from typing import Iterable

from treehornx.enum_models.core.Dir import Dir, Down, Up
from treehornx.enum_models.Lab.helpers import get_pfield_ptr, is_pfield_implicit, last_upd, points_here
from treehornx.enum_models.Lab.Lab import Lab


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


def field_trails(sigma: Lab, k: int) -> Iterable[tuple[int, int]]:
    """(p, i) for every pointer field pf whose final value is the target of p: child_is_ptr(σ, pf, p, i)."""
    for pfield in range(k):
        ptr = get_pfield_ptr(sigma, len(sigma), pfield)
        if ptr is not None:
            yield ptr


def child_is_struct(sigma: Lab, j: int, k: int) -> bool:
    """child_is_struct(σ, j): at the end, the j-th pointer field of the node still holds its input child, which
    exists."""
    return j < k and is_pfield_implicit(sigma, len(sigma), j) and sigma[1].active_child[j]
