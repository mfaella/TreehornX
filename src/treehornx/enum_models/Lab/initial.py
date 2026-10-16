"""Initial labels and pairs of the Lab encoding (CAV25, Appendix C.1, C.2, C.4).

Fields left unconstrained by the paper take the default value of their type: False for
bool, 0 for int and NOP for event.
"""

from itertools import product
from typing import Iterable

from treehornx import ir
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab.Event import NOP, Here
from treehornx.enum_models.Lab.Frame import Frame


def _first_frame(num_ptrs: int, active: bool, active_child: tuple[bool, ...]) -> Frame:
    return Frame(
        active=active,
        pc=0,
        upd=(False,) * num_ptrs,
        isnil=(False,) * num_ptrs,
        event=NOP(),
        active_child=active_child,
    )


def backbone_labels(function: ir.Function, m: int) -> Iterable[Label[Frame]]:
    """Labels of non-root nodes before the lace reaches them (CHC I).

    first_frame(f) = f.active ∧ ∧_{j∈[k+1,k+m]} ¬f.active_child_j ∨
                     ¬f.active ∧ ∧_{j∈[k+1,k+m]} f.active_child_j

    The active_child flags of the first k children of an active node encode the shape of
    the input tree, so every combination is generated; for an inactive node they are
    unconstrained and default to False.
    """
    k, num_ptrs = function.node.k, len(function.pointer_vars)
    for named in product((True, False), repeat=k):
        yield Label(_first_frame(num_ptrs, True, named + (False,) * m))
    yield Label(_first_frame(num_ptrs, False, (False,) * k + (True,) * m))


def start_labels(function: ir.Function, m: int) -> Iterable[Label[Frame]]:
    """Labels of the root holding the first frame of the lace (CHC II, predicate start).

    The first frame copies active and active_child from the second one (Section 3.1), the
    second frame has prev = (−, 2) as required by initial(σ).
    """
    k, num_ptrs, root = function.node.k, len(function.pointer_vars), function.ROOT
    second_frames: list[Frame] = []
    # non-empty input tree
    for named in product((True, False), repeat=k):
        second_frames.append(
            Frame(
                active=True,
                pc=0,
                upd=(False,) * num_ptrs,
                isnil=tuple(p != root for p in range(num_ptrs)),
                event=Here(root),
                active_child=named + (False,) * m,
            )
        )
    # empty input tree
    second_frames.append(
        Frame(
            active=False,
            pc=0,
            upd=(False,) * num_ptrs,
            isnil=(True,) * num_ptrs,
            event=NOP(),
            active_child=(False,) * (k + m),
        )
    )
    for f2 in second_frames:
        f1 = _first_frame(num_ptrs, f2.active, f2.active_child)
        yield Label(f2, prev=(Internal(), 2), prefix=Label(f1))


def is_initial(sigma: Label[Frame]) -> bool:
    """initial(σ) = ¬σ.avail^2 ∧ σ.prev^2 = (−, 2)"""
    return len(sigma) >= 2 and sigma.cut(2).prev == (Internal(), 2)


def consistent_first_frames(tau: Label[Frame], j: int, sigma: Label[Frame], k: int) -> bool:
    """(initial(σ) ∨ σ.active^1) ∧ (τ.active^1 → σ.active^1) ∧ (j > k → ¬τ.active^1) ∧
    σ.active_child^1_j = τ.active^1

    The child index j is 0-based, so the auxiliary children are those with j >= k.
    """
    sigma_1, tau_1 = sigma[1], tau[1]
    return (
        (is_initial(sigma) or sigma_1.active)
        and (not tau_1.active or sigma_1.active)
        and (j < k or not tau_1.active)
        and sigma_1.active_child[j] == tau_1.active
    )


def initial_pairs(
    function: ir.Function, m: int, starts: Iterable[Label[Frame]], backbones: Iterable[Label[Frame]]
) -> Iterable[Pair[Frame]]:
    """Pairs (σ, τ, j) where τ is the label of the j-th child of σ before the lace reaches it.

    With a single frame in τ, consistent_child reduces to consistent_first_frames.
    """
    k = function.node.k
    backbones = list(backbones)
    for sigma in [*starts, *backbones]:
        for tau in backbones:
            for j in range(k + m):
                if consistent_first_frames(tau, j, sigma, k):
                    yield Pair(sigma, tau, j)
