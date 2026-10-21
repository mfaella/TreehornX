"""Initial labels and pairs of the Lab encoding (CAV25, Appendix C.1, C.2, C.4).

Fields left unconstrained by the paper take the default value of their type: False for
bool, 0 for int and NOP for event.
"""

from itertools import product
from typing import Iterable

from treehornx import ir
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab.Event import NOP, Here
from treehornx.enum_models.Lab.Frame import Frame
from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Lab.next_dir import predict_next_dir


def _first_frame(num_ptrs: int, active: bool, active_child: tuple[bool, ...]) -> Frame:
    return Frame(
        active=active,
        pc=0,
        upd=(False,) * num_ptrs,
        isnil=(False,) * num_ptrs,
        event=NOP(),
        active_child=active_child,
        prev=None,
        next=None,
    )


def input_shapes(function: ir.Function) -> Iterable[tuple[bool, ...]]:
    """active_child flags of the first k children of an input node: a field declared nil by default never points
    to an input child."""
    nil_fields = function.node.nil_fields
    return product(*(((False,) if j in nil_fields else (True, False)) for j in range(function.node.k)))


def backbone_labels(function: ir.Function, m: int) -> Iterable[Lab]:
    """Labels of non-root nodes before the lace reaches them (CHC I).

    first_frame(f) = f.active ∧ ∧_{j∈[k+1,k+m]} ¬f.active_child_j ∨
                     ¬f.active ∧ ∧_{j∈[k+1,k+m]} f.active_child_j

    The active_child flags of the first k children of an active node encode the shape of
    the input tree, so every combination is generated (see `input_shapes`); for an inactive
    node they are unconstrained and default to False.
    """
    k, num_ptrs = function.node.k, len(function.pointer_vars)
    for named in input_shapes(function):
        yield Lab(_first_frame(num_ptrs, True, named + (False,) * m))
    yield Lab(_first_frame(num_ptrs, False, (False,) * k + (True,) * m))


def start_labels(function: ir.Function, m: int, n: int) -> Iterable[Lab]:
    """Labels of the root holding the first frame of the lace (CHC II, predicate start).

    The first frame copies active and active_child from the second one (Section 3.1), the
    second frame has prev = − as required by initial(σ).
    """
    k, num_ptrs, root = function.node.k, len(function.pointer_vars), function.ROOT
    second_frames: list[Frame] = []
    # non-empty input tree
    for named in input_shapes(function):
        second_frames.append(
            Frame(
                active=True,
                pc=0,
                upd=(False,) * num_ptrs,
                isnil=tuple(p != root for p in range(num_ptrs)),
                event=Here(root),
                active_child=named + (False,) * m,
                prev=Internal(),
                next=None,
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
            prev=Internal(),
            next=None,
        )
    )
    for f2 in second_frames:
        first = Lab(_first_frame(num_ptrs, f2.active, f2.active_child))
        second = f2.to_mut()
        second.next = predict_next_dir(function, m, n, first, second)
        yield Lab(second.to_frozen(), prefix=first)


def is_initial(sigma: Lab) -> bool:
    """initial(σ) = ¬σ.avail^2 ∧ σ.prev^2 = −: the frames of a non-root node are all entered from above or below"""
    return len(sigma) >= 2 and sigma[2].prev == Internal()


def consistent_first_frames(tau: Lab, j: int, sigma: Lab, k: int) -> bool:
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
    function: ir.Function, m: int, starts: Iterable[Lab], backbones: Iterable[Lab]
) -> Iterable[Pair[Lab]]:
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
