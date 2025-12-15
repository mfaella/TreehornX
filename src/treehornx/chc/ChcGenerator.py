import sys
from collections import deque
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import chain, count, product
from typing import Iterable

from frozendict import frozendict
from loguru import logger

from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.ir.instructions import *
from treehornx.ir.sorts import Enum, Pointer, Struct

from .core import Frame, FrameBuilder, Label, Pair
from .core.dir import Down, Internal
from .core.event import ERR, LOF, NOP, OOM, Exit, Here
from .PairDB import PairDB
from .SMT2FileBuilder import SMT2FileBuilder
from .Stepper import StepKind, Stepper

logger.remove(0)
logger.add(sys.stdout, level="TRACE")


@dataclass
class ChcGenerator:
    function: Function
    root: Var
    m: int
    n: int
    k: int = field(init=False)
    db: PairDB = field(init=False, default_factory=PairDB)
    _step_cache: dict[Pair, tuple[Frame, Frame | None, StepKind] | None] = field(init=False, default_factory=lambda: {})

    def __post_init__(self):
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        self.k = sum(1 for f in root_sort.fields.values() if f.sort.is_ptr())
        self.stepper = Stepper(self.function, self.k, self.m, self.n)

    @cached_property
    def pointers(self) -> tuple[Var, ...]:
        return tuple(p for p in self.function.vars if p.sort.is_ptr())

    @cached_property
    def named_children_keys(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.root.sort.pointee.fields.values() if p.sort.is_ptr())

    @cached_property
    def indexed_children_keys(self) -> tuple[int, ...]:
        return tuple(range(self.k, self.k + self.m))

    @cached_property
    def children_keys(self) -> tuple[str | int, ...]:
        return (*self.named_children_keys, *self.indexed_children_keys)

    def enum_vars(self) -> Iterable[Var]:
        return (e for e in self.function.vars if e.sort.is_enum())

    def enum_fields(self) -> Iterable[Var]:
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        for var in root_sort.fields.values():
            if var.sort.is_enum():
                yield var

    def enums_products(self, vars: Iterable[Var]) -> Iterable[frozendict[str, str]]:
        vars = list(vars)
        assert all(isinstance(v.sort, Enum) for v in vars)
        values: Iterable[tuple[str, ...]] = (tuple(var.sort.flags.keys()) for var in vars)  # type: ignore
        for prod in product(*values):
            yield frozendict({var.name: val for var, val in zip(vars, prod)})

    def active_child_products(self) -> Iterable[frozendict[str | int, bool]]:
        for bits in product([True, False], repeat=len(self.named_children_keys)):
            yield frozendict(
                chain(zip(self.named_children_keys, bits), ((i, False) for i in self.indexed_children_keys))
            )

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
                active_child=frozendict({key: True for key in self.children_keys}),
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
            frame_builder.prev = (Internal(), 0)
            assert all(first_frame.isnil.values())
            if frame_builder.active:
                frame_builder.event = Here(self.root.name)
                frame_builder.isnil[self.root.name] = False
            else:
                frame_builder.event = NOP()
                frame_builder.active_child = {key: False for key in self.children_keys}
            yield first_frame, frame_builder.build()

    def start_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.start_frames(), self.first_frames(), self.children_keys):
            if parent[1].active_child[child_key] == child.active:
                parent_lab = Label.make(*parent)
                child_lab = Label.make(child)
                pair = Pair(parent=parent_lab, child=child_lab, child_key=child_key)
                # logger.debug(
                #     f"Creating initial pair: parent.active={parent[1].active} parent.active_child[{child_key}]={parent[1].active_child[child_key]} child.active={child.active}"
                # )
                yield pair

    def first_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.first_frames(), self.first_frames(), self.children_keys):
            if parent.active_child[child_key] == child.active:
                parent_lab = Label.make(parent)
                child_lab = Label.make(child)
                pair = Pair(parent=parent_lab, child=child_lab, child_key=child_key)
                # logger.debug(
                #     f"Creating initial pair: parent.active={parent[1].active} parent.active_child[{child_key}]={parent[1].active_child[child_key]} child.active={child.active}"
                # )
                yield pair

    def update_after_internal_step(self, pair: Pair, frame: Frame) -> Iterable[Pair]:
        pairs = list(self.db.find_by_leader(leader=pair.leader()))
        for p in pairs:
            new_p = p.extended_with_internal_frame(frame)
            self.db.add(new_p)
            yield new_p

    def update_after_external_step(self, pair: Pair, frame: Frame) -> Iterable[Pair]:
        new_pair = pair.extended_with_external_frame(frame)
        yield new_pair
        new_pairs = [new_pair]
        for p in self.db.find_by_leader(leader=pair.follower()):
            if p.dir() != pair.rev_dir() or not self.is_continuity_pair(p):
                new_leader = p.leader().extended_with(frame)
                new_p = p.updated_with_leader(new_leader)
                new_pairs.append(new_p)

        for new_p in new_pairs:
            self.db.add(new_p)

        return new_pairs

    def _step(self, pair: Pair) -> tuple[FrameBuilder, FrameBuilder | None, StepKind] | None:
        return Stepper(self.function, self.k, self.m, self.n).step(pair)

    def psi_internal(self, frameb: FrameBuilder) -> Frame:
        for ptr in self.pointers:
            frameb.upd[ptr.name] = False
        return frameb.build()

    def psi_external(self, pair: Pair, frameb: FrameBuilder) -> Frame:
        if pair.follower()[-1].index <= 1:
            for p in self.pointers:
                frameb.upd[p.name] = False
        else:
            frames = tuple(pair.leader().slice(2))
            a_ = max(f.index for f in pair.leader().slice(1) if f.prev[0] == pair.dir())  # type: ignore
            for p in self.pointers:
                frameb.upd[p.name] = any(f.event == Here(p.name) or f.upd[p.name] for f in pair.leader().slice(a_))

        return frameb.build()

    def step(self, pair: Pair) -> tuple[Frame, Frame | None, StepKind] | None:
        if pair not in self._step_cache:
            if isinstance(pair.leader()[-1].event, (OOM, ERR, LOF, Exit)):
                self._step_cache[pair] = None
                return None

            step_result = self._step(pair)
            if step_result is None:
                return None
            tau_b_builder, tau_b_false_builder, step_kind = step_result
            if step_kind == StepKind.INTERNAL:
                tau_b_builder.index = len(pair.leader())
                frame = self.psi_internal(tau_b_builder)
                if tau_b_false_builder is None:
                    self._step_cache[pair] = (frame, None, step_kind)
                else:
                    tau_b_false_builder.index = len(pair.leader())
                    frame_false = self.psi_internal(tau_b_false_builder)
                    self._step_cache[pair] = (frame, frame_false, step_kind)
            else:
                tau_b_builder.index = len(pair.follower())
                tau_b = self.psi_external(pair, tau_b_builder)
                self._step_cache[pair] = (tau_b, None, step_kind)
        return self._step_cache[pair]

    def is_continuity_pair(self, pair: Pair) -> bool:
        return self.step(pair) is not None

    def generate(self) -> SMT2FileBuilder:
        smt2file = SMT2FileBuilder(
            {v for v in self.function.vars if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},
            {v for v in self.root.sort.pointee.fields.values() if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},  # type: ignore
        )
        processed: set[Pair] = set()
        queue: deque[Pair] = deque()

        # yielding assertion of first and start frames
        for f in self.start_frames():
            smt2file.assert_fact(Label.make(*f))
        for f in self.first_frames():
            smt2file.assert_fact(Label.make(f))

        for pair in self.start_pairs():
            self.db.add(pair)
            queue.append(pair)

        for pair in self.first_pairs():
            self.db.add(pair)

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
                for pair in self.db.find_by_leader(pair.leader()):
                    processed.add(pair)
                for frame in new_frames:
                    # update pairs db
                    queue.extend(self.update_after_internal_step(pair, frame))
                    # assert internal step
                    label = pair.leader().extended_with(frame)
                    if not isinstance(frame.event, Exit):
                        inst = self.function.instructions[label[-2].pc]
                        smt2file.assert_internal_step(label, inst)
            else:
                # update pairs db
                queue.extend(self.update_after_external_step(pair, tau_b))

                # assert external step for tau_b
                new_pair = pair.extended_with_external_frame(tau_b)
                smt2file.assert_external_step(new_pair)

        logger.info("All pair have been generated")
        return smt2file
