from collections import deque
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import chain, count, product
from typing import Iterable

from chc.core.dir import Down
from chc.SMT2FileBuilder import SMT2FileBuilder
from frozendict import frozendict
from ir.expressions import Var
from ir.function import Function
from ir.instructions import *
from ir.sorts import Enum, Struct

from .core import Frame, FrameBuilder, Label, Pair
from .core.event import NOP, Here
from .PairDB import PairDB
from .Stepper import StepKind, Stepper


@dataclass
class ChcGenerator:
    function: Function
    root: Var
    m: int
    n: int
    k: int = field(init=False)
    db: PairDB = field(default_factory=PairDB)
    _generated: bool = field(default=False, init=False)

    def __post_init__(self):
        root_sort = self.root.sort
        assert isinstance(root_sort, Struct)
        self.k = sum(1 for f in root_sort.fields.values() if f.sort.is_ptr())
        self.stepper = Stepper(self.function, self.k, self.m, self.n)

    @cached_property
    def pointers(self) -> tuple[Var, ...]:
        return tuple(p for p in self.function.vars if p.sort.is_ptr())

    @cached_property
    def child_keys(self) -> tuple[str | int, ...]:
        pointers_names = tuple(p.name for p in self.pointers)
        indices = tuple(range(self.k, self.k + self.m))
        return pointers_names + indices

    def enum_vars(self) -> Iterable[Var]:
        return (e for e in self.function.vars if e.sort.is_enum())

    def enum_fields(self) -> Iterable[Var]:
        root_sort = self.root.sort
        assert isinstance(root_sort, Struct)
        for var in root_sort.fields.values():
            if var.sort.is_enum():
                yield var

    def enums_products(self, vars: Iterable[Var]) -> Iterable[frozendict[str, str]]:
        assert all(isinstance(v.sort, Enum) for v in (vars := list(vars)))
        values: Iterable[tuple[str, ...]] = (tuple(var.sort.flags.keys()) for var in vars)  # type: ignore
        for prod in product(*values):
            yield frozendict({var.name: val for var, val in zip(vars, prod)})

    def active_child_products(self) -> Iterable[frozendict[str | int, bool]]:
        pointers_names = (p.name for p in self.pointers)

        for bits in product([True, False], repeat=len(self.pointers)):
            yield frozendict(chain(zip(pointers_names, bits), ((i, False) for i in range(self.k, self.k + self.m))))

    def first_frames(self) -> Iterable[Frame]:
        upd: frozendict[str, bool] = frozendict({p.name: False for p in self.pointers})
        isnil: frozendict[str, bool] = frozendict({p.name: True for p in self.pointers})

        enum_values_product = self.enums_products(self.enum_vars())
        enum_fields_product = self.enums_products(self.enum_fields())
        for enum_values, enum_fields in product(enum_values_product, enum_fields_product):
            for active_child in self.active_child_products():
                active_frame = Frame(
                    index=0,
                    active=True,
                    pc=0,
                    upd=upd,
                    isnil=isnil,
                    event=NOP(),
                    active_child=active_child,
                    enum_values=enum_values,
                    enum_fields=enum_fields,
                    prev=None,
                )
                yield active_frame
            inactive_frame = Frame(
                index=0,
                active=False,
                pc=0,
                upd=upd,
                isnil=isnil,
                event=NOP(),
                active_child=frozendict(
                    {key: True for key in chain((p.name for p in self.pointers), range(self.k, self.k + self.m))}
                ),
                enum_values=frozendict({}),
                enum_fields=frozendict({}),
                prev=None,
            )
            yield inactive_frame

    def start_frames(self) -> Iterable[tuple[Frame, Frame]]:
        for first_frame in self.first_frames():
            frame_builder = FrameBuilder(base=first_frame)
            frame_builder.index = 1
            frame_builder.active = first_frame.active
            assert not any(first_frame.isnil.values())
            if frame_builder.active:
                frame_builder.event = Here(self.root.name)
                frame_builder.isnil[self.root.name] = False
            else:
                frame_builder.event = NOP()
                frame_builder.active_child = {key: False for key in self.child_keys}
            yield first_frame, frame_builder.build()

    def inital_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.start_frames(), self.first_frames(), self.child_keys):
            if parent[1].active_child[child_key] == child.active:
                parent_lab = Label.make(*parent)
                child_lab = Label.make(child)
                pair = Pair(parent=parent_lab, child=child_lab, child_key=child_key)
                yield pair

    def update_after_internal_step(self, pair: Pair, frame: Frame) -> Iterable[Pair]:
        for p in self.db.find_by(leader=pair.leader()):
            new_p = p.extend_with_internal_frame(frame)
            self.db.add(new_p)
            yield new_p

    def update_after_external_step(self, pair: Pair, frame: Frame) -> Iterable[Pair]:
        new_pair = pair.extend_with_external_frame(frame)
        self.db.add(new_pair)
        yield new_pair
        for p in self.db.find_by(leader=pair.follower()):
            if p.dir() != pair.rev_dir() or not self.is_continuity_pair(p):
                new_leader = p.leader().extended_with(frame)
                new_p = p.updated_with_leader(new_leader)
                self.db.add(new_p)
                yield new_p

    def _step(self, pair: Pair) -> tuple[FrameBuilder, FrameBuilder | None, StepKind] | None:
        return Stepper(self.function, self.k, self.m, self.n).step(pair)

    def psi_internal(self, frameb: FrameBuilder) -> Frame:
        for ptr in self.pointers:
            frameb.upd[ptr.name] = False
        return frameb.build()

    def psi_external(self, pair: Pair, frameb: FrameBuilder) -> Frame:
        if pair.leader()[-1].index <= 1:
            for p in self.pointers:
                frameb.upd[p.name] = False
        else:
            a_ = max(f.index for f in pair.leader().frames[1:] if f.prev[0] == pair.dir())  # type: ignore
            for p in self.pointers:
                frameb.upd[p.name] = any(f.event == Here(p.name) or f.upd[p.name] for f in pair.leader().frames[a_:])

        return frameb.build()

    @cache
    def step(self, pair: Pair) -> tuple[Frame, Frame | None, StepKind] | None:
        step_result = self._step(pair)
        if step_result is None:
            return None
        tau_b_builder, tau_b_false_builder, step_kind = step_result
        if step_kind == StepKind.INTERNAL:
            if tau_b_false_builder is None:
                frame = self.psi_internal(tau_b_builder)
                return frame, None, step_kind
            else:
                frame_true = self.psi_internal(tau_b_builder)
                frame_false = self.psi_internal(tau_b_false_builder)
                return frame_true, frame_false, step_kind
        else:
            tau_b = self.psi_external(pair, tau_b_builder)
            tau_b_false = None
            if tau_b_false_builder is not None:
                tau_b_false = self.psi_external(pair, tau_b_false_builder)
            return tau_b, tau_b_false, step_kind

    def is_continuity_pair(self, pair: Pair) -> bool:
        return self.step(pair) is not None

    def generate(self) -> SMT2FileBuilder:
        smt2file = SMT2FileBuilder(self.function.vars, self.root.sort.fields)  # type: ignore
        processed: set[Pair] = set()
        queue: deque[Pair] = deque()

        # yielding assertion of first and start frames
        for f in self.start_frames():
            smt2file.assert_fact(Label.make(*f))
        for f in self.first_frames():
            smt2file.assert_fact(Label.make(f))

        for pair in self.inital_pairs():
            self.db.add(pair)
            queue.append(pair)

        while queue:
            pair = queue.popleft()
            if pair in processed:
                continue
            processed.add(pair)
            step_result = self.step(pair)
            if step_result is None:
                continue
            tau_b, tau_b_false, step_kind = step_result
            new_frames = (tau_b,) if tau_b_false is None else (tau_b, tau_b_false)
            if step_kind == StepKind.INTERNAL:
                for frame in new_frames:
                    # update pairs db
                    queue.extend(self.update_after_internal_step(pair, frame))
                    # assert internal step
                    label = pair.leader().extended_with(frame)
                    inst = self.function.instructions[label[-2].pc]
                    smt2file.assert_internal_step(label, inst)
            else:
                # update pairs db
                queue.extend(self.update_after_external_step(pair, tau_b))

                # assert external step for tau_b

                new_pair = pair.extend_with_external_frame(tau_b)
                smt2file.assert_external_step(pair)

        return smt2file
