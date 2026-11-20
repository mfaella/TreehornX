"""The labels of the knitted trees.

* `Lab` (CAV25): the log of frames of a node, an immutable linked list of frames: the top frame and the label below
  it (`prefix`). Positions are 1-based like the paper (`label[1]` is the first frame, `label[len(label)]` the top
  one). Equality walks the prefixes, the hash (cached) includes the prefix.
* `TLab`: a `Lab` with its tainting flags (POPL27, Sec. 6). `LabEngine` emits every label as a `TLab` with no taint
  (`untainted`); only `TaintingEngine` (tree-shape and postcondition checks) changes the flags.
* `ExitCode`: how the lace ends in a label.

`Lab` and `TLab` are interned (`treehornx.intern`, weak pools): `Lab.make(frame=..., prefix=...)` and
`TLab.make(taint_node=..., taint_ptr=..., lab=...)` give the canonical instance of a label; a prefix is always
canonical, because it was built by `make`. `get_tlab_id` numbers the TLabs (the names of the predicates).

The initial labels and pairs of the Lab encoding (CAV25, Appendix C.1, C.2, C.4) are built at the end
(`start_labels`, `backbone_labels`, `initial_pairs`, as untainted TLabs). Fields left unconstrained by the paper
take the default value of their type: False for bool, 0 for int and NOP for event.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from enum import Enum
from itertools import count, islice, product
from typing import TYPE_CHECKING, Callable, Iterable, Protocol, overload

from typing_extensions import override

from treehornx.symbolic_tree import Edge
from treehornx.enum_models.enviroment import Env, global_env
from treehornx.enum_models.tainting import BoolPlus, TaintPtr
from treehornx.intern import intern

@dataclass(slots=True, frozen=True)
class Up:
    pass


@dataclass(slots=True, frozen=True)
class Internal:
    pass


@dataclass(slots=True, frozen=True)
class Down:
    child: int


Dir = Up | Internal | Down


def are_opposite_directions(dir1: Dir, dir2: Dir) -> bool:
    return (
        (isinstance(dir1, Up) and isinstance(dir2, Down))
        or (isinstance(dir1, Down) and isinstance(dir2, Up))
        or (isinstance(dir1, Internal) and isinstance(dir2, Internal))
    )


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NOP:
    pass


@dataclass(frozen=True)
class ERR:
    pass


@dataclass(frozen=True)
class OOM:
    pass


@dataclass(frozen=True)
class LOF:
    """label overflow"""

    pass


@dataclass(slots=True, frozen=True)
class FieldAssignP:
    pfield: int
    p: int | None


@dataclass(slots=True, frozen=True)
class Here:
    p: int


@dataclass(slots=True, frozen=True)
class FieldHere:
    pfield: int


@dataclass(slots=True, frozen=True)
class Rewind:
    i: int


@dataclass(slots=True, frozen=True)
class RwdSpec:
    i: int
    p: int


@dataclass(frozen=True)
class Exit:
    pass


Event = NOP | OOM | ERR | FieldAssignP | Here | Rewind | RwdSpec | Exit | LOF | FieldHere


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class Frame:
    active: bool
    pc: int
    upd: tuple[bool, ...]
    isnil: tuple[bool, ...]
    event: Event
    active_child: tuple[bool, ...]
    prev: Dir | None
    # direction in which the lace leaves the frame, None when it never does
    next: Dir | None

    def to_mut(self) -> MutableFrame:
        return MutableFrame(
            self.active,
            self.pc,
            list(self.upd),
            list(self.isnil),
            self.event,
            list(self.active_child),
            self.prev,
            self.next,
        )


@dataclass(slots=True)
class MutableFrame:
    """A frame under construction.

    Every field starts unset (None) and is filled phase by phase: first by the step that
    sets the fields specific to the instruction, then by `default` for the remaining ones
    and finally by the Psi predicate that computes `upd`. `to_frozen` checks that no field
    has been forgotten."""

    active: bool | None = None
    pc: int | None = None
    upd: list[bool] | None = None
    isnil: list[bool] | None = None
    event: Event | None = None
    active_child: list[bool] | None = None
    prev: Dir | None = None
    # set last, by predict_next_dir; None is a valid value (the lace never leaves the frame)
    next: Dir | None = None

    def to_frozen(self) -> Frame:
        assert self.active is not None, "field 'active' of the new frame has not been set"
        assert self.pc is not None, "field 'pc' of the new frame has not been set"
        assert self.upd is not None, "field 'upd' of the new frame has not been set"
        assert self.isnil is not None, "field 'isnil' of the new frame has not been set"
        assert self.event is not None, "field 'event' of the new frame has not been set"
        assert self.active_child is not None, "field 'active_child' of the new frame has not been set"
        assert self.prev is not None, "field 'prev' of the new frame has not been set"
        return Frame(
            self.active,
            self.pc,
            tuple(self.upd),
            tuple(self.isnil),
            self.event,
            tuple(self.active_child),
            self.prev,
            self.next,
        )



class ExitCode(Enum):
    N = 0  # None
    C = 1  # Clean
    M = 2  # Memory
    E = 3  # Error
    O = 4  # Overflow  # noqa: E741


@intern
@dataclass(frozen=True, slots=True, weakref_slot=True)
class Lab:
    frame: Frame
    prefix: Lab | None = field(default=None)
    _hash: int = field(init=False)
    _length: int = field(init=False)

    if TYPE_CHECKING:

        @staticmethod
        def make(*, frame: Frame, prefix: Lab | None = None) -> Lab: ...

    def __post_init__(self) -> None:
        # the prefix hash is cached, so including it is O(1) and keeps labels with different histories apart
        prefix_hash = None if self.prefix is None else self.prefix._hash
        object.__setattr__(self, "_hash", hash((self.frame, prefix_hash)))
        object.__setattr__(self, "_length", 1 + (len(self.prefix) if self.prefix is not None else 0))

    def __iter__(self) -> Iterable[Frame]:
        return iter(self[1 : len(self)])

    def __reversed__(self) -> Iterable[Frame]:
        return (label.frame for label in self._prefixes())

    @overload
    def __getitem__(self, index: int) -> Frame: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Frame, ...]: ...

    def __getitem__(self, index: int | slice) -> Frame | tuple[Frame, ...]:
        match index:
            case int():
                if not 1 <= index <= len(self):
                    raise IndexError(index)
                return self.cut(index).frame
            case slice():
                assert index.step is None, "slicing with step is not supported"
                start = 1 if index.start is None else index.start
                stop = len(self) if index.stop is None else min(len(self), index.stop)  # inclusive stop
                start, stop = len(self) - stop, len(self) - start + 1
                prefixes = islice(self._prefixes(), start, stop)
                return tuple(reversed([label.frame for label in prefixes]))

    def __len__(self) -> int:
        return self._length

    @override
    def __hash__(self) -> int:
        return self._hash

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Lab):
            return NotImplemented
        a: Lab | None = self
        b: Lab | None = other
        while a is not None and b is not None:
            if a is b:
                return True
            if a._hash != b._hash or a._length != b._length or a.frame != b.frame:
                return False
            a, b = a.prefix, b.prefix
        return a is b

    def cut(self, index: int) -> Lab:
        """The label of the first `index` frames."""
        return next(islice(self._prefixes(), len(self) - index, None))

    def _prefixes(self) -> Iterable[Lab]:
        current: Lab | None = self
        while current is not None:
            yield current
            current = current.prefix

    def iter_indexed(self, start: int, stop: int) -> Iterable[tuple[int, Frame]]:
        return enumerate(self[start:stop], start=start)

    def reversed_iter_indexed(self, start: int, stop: int) -> Iterable[tuple[int, Frame]]:
        frames = self[start:stop]
        return zip(range(start + len(frames) - 1, start - 1, -1), reversed(frames))


@intern
@dataclass(frozen=True, slots=True, weakref_slot=True)
class TLab:
    """T(σ, taint, taint_ptr): a label with the tainting flags of its node and of its pointer trails."""

    taint_node: BoolPlus
    taint_ptr: TaintPtr
    lab: Lab

    if TYPE_CHECKING:

        @staticmethod
        def make(*, taint_node: BoolPlus, taint_ptr: TaintPtr, lab: Lab) -> TLab: ...


# ---------------------------------------------------------------------------
# factories
# ---------------------------------------------------------------------------


class TLabFactory(Protocol):
    """Builds a TLab from its fields; the engines build every TLab through one (`TLab.make` by default)."""

    def __call__(self, *, taint_node: BoolPlus, taint_ptr: TaintPtr, lab: Lab) -> TLab: ...


_NO_TAINT = TaintPtr()


def untainted(lab: Lab) -> TLab:
    """The TLab of `lab` with no taint (⊥ node, no trail)."""
    return TLab.make(taint_node=BoolPlus.Bottom, taint_ptr=_NO_TAINT, lab=lab)


_tlab_ids: "weakref.WeakKeyDictionary[TLab, int]" = weakref.WeakKeyDictionary()
_next_tlab_id = count()


def get_tlab_id(tlab: TLab) -> int:
    """The id of `tlab`, assigned the first time it is asked (ids grow in the order of the requests); an equal TLab
    has the same id as long as one of them is alive."""
    tlab_id = _tlab_ids.get(tlab)
    if tlab_id is None:
        tlab_id = next(_next_tlab_id)
        _tlab_ids[tlab] = tlab_id
    return tlab_id


# ---------------------------------------------------------------------------
# initial labels and pairs (CAV25, Appendix C.1, C.2, C.4)
# ---------------------------------------------------------------------------


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


def input_shapes(e: Env = global_env()) -> Iterable[tuple[bool, ...]]:
    """active_child flags of the first k children of an input node: the parent field never points to an input
    child."""
    node = e.func.node
    return product(*(((True, False) if node.is_child_field(j) else (False,)) for j in range(e.k)))


def backbone_labels(e: Env = global_env()) -> Iterable[TLab]:
    """Labels of non-root nodes before the lace reaches them (CHC I).

    first_frame(f) = f.active ∧ ∧_{j∈[k+1,k+m]} ¬f.active_child_j ∨
                     ¬f.active ∧ ∧_{j∈[k+1,k+m]} f.active_child_j

    The active_child flags of the first k children of an active node encode the shape of
    the input tree, so every combination is generated (see `input_shapes`); for an inactive
    node they are unconstrained and default to False.
    """
    k, m = e.k, e.m
    num_ptrs = len(e.func.pointer_vars)
    for named in input_shapes(e):
        yield untainted(Lab.make(frame=_first_frame(num_ptrs, True, named + (False,) * m)))
    yield untainted(Lab.make(frame=_first_frame(num_ptrs, False, (False,) * k + (True,) * m)))


def start_labels(
    predict_next: Callable[[Lab, MutableFrame], Dir | None], e: Env = global_env()
) -> Iterable[TLab]:
    """Labels of the root holding the first frame of the lace (CHC II, predicate start).

    The first frame copies active and active_child from the second one (Section 3.1), the
    second frame has prev = − as required by initial(σ). `predict_next` sets the next direction of the second frame
    (`LabEngine.predict_next_dir`).
    """
    k, m, function = e.k, e.m, e.func
    num_ptrs, root = len(function.pointer_vars), function.ROOT
    second_frames: list[Frame] = []
    # non-empty input tree
    for named in input_shapes(e):
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
        first = Lab.make(frame=_first_frame(num_ptrs, f2.active, f2.active_child))
        second = f2.to_mut()
        second.next = predict_next(first, second)
        yield untainted(Lab.make(frame=second.to_frozen(), prefix=first))


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
    starts: Iterable[TLab], backbones: Iterable[TLab], e: Env = global_env()
) -> Iterable[Edge[TLab]]:
    """Pairs (σ, τ, j) where τ is the label of the j-th child of σ before the lace reaches it.

    With a single frame in τ, consistent_child reduces to consistent_first_frames.
    """
    k, m = e.k, e.m
    backbones = list(backbones)
    for sigma in [*starts, *backbones]:
        for tau in backbones:
            for j in range(k + m):
                if consistent_first_frames(tau.lab, j, sigma.lab, k):
                    yield Edge(sigma, tau, j)
