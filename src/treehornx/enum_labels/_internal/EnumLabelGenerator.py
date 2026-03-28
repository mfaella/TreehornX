from collections import deque
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import chain, product
from typing import Iterable

from frozendict import frozendict

from treehornx.enum_labels.core.Frame import Frame, FrameDescriptor
from treehornx.enum_labels.core.Label import Label
from treehornx.enum_labels.core.Dir import Internal
from treehornx.enum_labels.core.Event import NOP, Here
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.ir.instructions import *
from treehornx.ir.sorts import Enum, Pointer, Struct

from .knitter.CompressedBoundedInternalChainKnitter import CompressedBoundedInternalChainKnitter
from .knitter.CompressedUnboundedInternalChainKnitter import CompressedUnboundedInternalChainKnitter
from .knitter.IKnitter import IKnitter
from .knitter.KnitResult import ExternalStepResult, InternalStepResult, KnitResult, StepFailed
from .knitter.Pair import LeadershipKind, Pair
from .StatesDB import StatesDB


@dataclass
class EnumLabelGenerator:
    function: Function
    root: Var
    m: int
    n: int
    internal_chain_bound: int | None = None
    k: int = field(init=False)
    db: StatesDB = field(init=False, default_factory=StatesDB)

    def __post_init__(self):
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        self.k = sum(1 for f in root_sort.fields.values() if f.sort.is_ptr())

    @cached_property
    def _pointers(self) -> tuple[Var, ...]:
        return tuple(p for p in self.function.vars if p.sort.is_ptr())

    @cached_property
    def _named_children_keys(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.root.sort.pointee.fields.values() if p.sort.is_ptr())

    @cached_property
    def _indexed_children_keys(self) -> tuple[int, ...]:
        return tuple(range(self.k, self.k + self.m))

    @cached_property
    def _children_keys(self) -> tuple[str | int, ...]:
        return (*self._named_children_keys, *self._indexed_children_keys)

    @cached_property
    def _enum_vars(self) -> tuple[Var, ...]:
        return tuple(e for e in self.function.vars if e.sort.is_enum())

    @cached_property
    def _enum_fields(self) -> tuple[Var, ...]:
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        return tuple(f for f in root_sort.fields.values() if f.sort.is_enum())

    def enums_products(self, vars: Iterable[Var]) -> Iterable[frozendict[str, str]]:
        vars = list(vars)
        assert all(isinstance(v.sort, Enum) for v in vars)
        values: Iterable[tuple[str, ...]] = (tuple(var.sort.flags.keys()) for var in vars)  # type: ignore
        for prod in product(*values):
            yield frozendict({var.name: val for var, val in zip(vars, prod)})

    def active_child_products(self) -> Iterable[frozendict[str | int, bool]]:
        for bits in product([True, False], repeat=len(self._named_children_keys)):
            yield frozendict(
                chain(zip(self._named_children_keys, bits), ((i, False) for i in self._indexed_children_keys))
            )

    def backbone_labels(self) -> Iterable[Label]:
        upd: frozendict[str, bool] = frozendict({p.name: False for p in self._pointers})
        isnil: frozendict[str, bool] = frozendict({p.name: True for p in self._pointers})

        # enum_values_product = self.enums_products(self.enum_vars())
        # enum_fields_product = self.enums_products(self.enum_fields())
        # for enum_values, enum_fields in product(enum_values_product, enum_fields_product):
        enum_values: frozendict[str, str] = frozendict({v.name: tuple(v.sort.flags)[0] for v in self._enum_vars})
        enum_fields: frozendict[str, str] = frozendict({f.name: tuple(f.sort.flags)[0] for f in self._enum_fields})
        for active_child in self.active_child_products():
            if active_child.get("parent", False):
                continue
            active_frame = Frame(
                index=0,
                active=True,
                pc=0,
                upd=upd,
                isnil=isnil,
                events=frozenset(),
                active_child=active_child,
                enum_vars=enum_values,
                enum_fields=enum_fields,
                prev=None,
            )
            yield self.db.make_label(None, active_frame)
        inactive_frame = Frame(
            index=0,
            active=False,
            pc=0,
            upd=upd,
            isnil=isnil,
            events=frozenset(),
            active_child=frozendict({key: True for key in self._children_keys}),
            enum_vars=enum_values,
            enum_fields=enum_fields,
            prev=None,
        )
        yield self.db.make_label(None, inactive_frame)

    def start_labels(self) -> Iterable[Label]:
        for backbone_label in self.backbone_labels():
            first_frame = backbone_label.frame
            frame_builder = FrameDescriptor()
            frame_builder.index = 1
            frame_builder.active = first_frame.active
            frame_builder.prev = (Internal(), 1)
            if frame_builder.active:
                frame_builder.event = Here(self.root.name)
                frame_builder.isnil[self.root.name] = False
            else:
                frame_builder.event = NOP()
                frame_builder.active_child = {key: False for key in self._children_keys}
            second_frame = Frame(
                index=1,
                active=first_frame.active,
                pc=0,
                upd=frozendict({key.name: False for key in self._pointers}),
                isnil=frozendict(
                    {key.name: key.name != self.root.name for key in self._pointers}
                    if first_frame.active
                    else {key.name: True for key in self._pointers}
                ),
                events=frozenset({Here(self.root.name)}) if first_frame.active else frozenset(),
                enum_fields=first_frame.enum_fields,
                enum_vars=first_frame.enum_vars,
                active_child=first_frame.active_child
                if first_frame.active
                else frozendict({key: False for key in self._children_keys}),
                prev=(Internal(), 1),
            )
            yield self.db.make_label(backbone_label, second_frame)

    def initial_root_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.start_labels(), self.backbone_labels(), self._children_keys):
            # parent_active = parent[1].active_child.get("parent", False)
            if parent[1].active_child[child_key] == child[0].active:  # and not parent_active:
                pair = Pair(parent=parent, child=child, child_key=child_key)
                yield pair

    def initial_internal_node_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.backbone_labels(), self.backbone_labels(), self._children_keys):
            # parent_active = parent[0].active_child.get("parent", False)
            if parent[0].active_child[child_key] == child[0].active:  # and not parent_active:
                pair = Pair(parent=parent, child=child, child_key=child_key)
                yield pair

    def _add_ancestor(self, label: Label, ancestor: Label) -> None:
        self.db.add_ancestor(label, ancestor)

    def _add_pair(self, pair: Pair) -> None:
        self.db.add_pair(pair)
        self.db.add_label(pair.leader())
        self.db.add_label(pair.follower())

    def _initialize_pairs(self):
        for pair in self.initial_root_pairs():
            self._add_pair(pair)
        for pair in self.initial_internal_node_pairs():
            self._add_pair(pair)

    def _make_knitter(self) -> IKnitter:
        def make_label(o: Label | None, f: Frame) -> Label:
            return self.db.make_label(o, f)

        def on_new_internal_step(ancestor_pair: Pair, lab_pair: Pair):
            self._add_ancestor(lab_pair.leader(), ancestor_pair.leader())

        def on_new_external_step(previous_pair: Pair, lab_pair: Pair):
            self._add_pair(lab_pair)

        if self.internal_chain_bound is None:

            def on_endless_loop_detected(pivot: Pair):
                self.db.set_endless_loop_pivot(pivot.leader())

            knitter = CompressedUnboundedInternalChainKnitter(
                self.function,
                self.k,
                self.m,
                self.n,
                make_label=make_label,
                on_endless_loop_detected=on_endless_loop_detected,
                on_new_internal_step=on_new_internal_step,
                on_new_external_step=on_new_external_step,
            )
        else:
            knitter = CompressedBoundedInternalChainKnitter(
                self.function,
                self.k,
                self.m,
                self.n,
                self.internal_chain_bound,
                make_label=make_label,
                on_new_internal_step=on_new_internal_step,
                on_new_external_step=on_new_external_step,
            )

        return knitter

    def generate(self):
        queue: deque[Pair] = deque(self.initial_root_pairs())

        self._initialize_pairs()

        knitter = self._make_knitter()

        @cache
        def knit(pair: Pair) -> KnitResult:
            return knitter.knit(pair)

        def is_continuos_pair(pair: Pair) -> bool:
            return knit(pair) != StepFailed()

        def qappend(pair: Pair):
            queue.append(pair)

        processed: set[Pair] = set()

        while queue:
            pair = queue.popleft()

            if self.db.is_endless_loop_pivot(pair.leader()):
                continue

            if pair in processed:
                continue

            processed.add(pair)

            knit_result = knit(pair)

            match knit_result:
                case StepFailed():  # non continuos pair
                    for extended_leader in self.db.get_connection_extensions(pair.leader()):
                        new_pair = pair.replace_leader(extended_leader)
                        self._add_pair(new_pair)
                        qappend(new_pair)
                case InternalStepResult(chain_end_pairs):  # internal steps
                    for chain_end_pair in chain_end_pairs:
                        new_leader = chain_end_pair.leader()
                        self.db.set_connection_label(new_leader)
                        assert pair in set(self.db.find_pairs_by_leader(pair.leader()))
                        for p in self.db.find_pairs_by_leader(pair.leader()):
                            parent = new_leader if p.leadership == LeadershipKind.PARENT else p.parent
                            child = new_leader if p.leadership == LeadershipKind.CHILD else p.child
                            leadership = p.leadership
                            child_key = p.child_key
                            new_p = Pair(parent, child, child_key, leadership)
                            self._add_pair(new_p)
                            qappend(new_p)
                            self._add_pair(new_p)
                case ExternalStepResult(pair=Pair(parent, child, child_key, leadership)):
                    qappend(knit_result.pair)

                    new_leader = parent if leadership == LeadershipKind.PARENT else child
                    self.db.set_connection_label(new_leader)
                    for p in self.db.find_pairs_by_leader(
                        pair.follower()
                    ):  # finding by follower because the leadership has been switched in the new pair
                        if (leadership != p.leadership or child_key != p.child_key) and not is_continuos_pair(p):
                            new_parent = new_leader if p.leadership == LeadershipKind.PARENT else p.parent
                            new_child = new_leader if p.leadership == LeadershipKind.CHILD else p.child
                            new_p = Pair(new_parent, new_child, p.child_key, p.leadership)
                            self._add_pair(new_p)
                            qappend(new_p)
