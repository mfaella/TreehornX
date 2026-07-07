from collections import deque
from dataclasses import dataclass, field
from functools import cache, cached_property
from itertools import chain, product
from typing import Callable, Iterable

from frozendict import frozendict
from loguru import logger

from treehornx.enum_labels.core.Dir import Internal
from treehornx.enum_labels.core.Event import NOP, Here
from treehornx.enum_labels.core.Frame import Frame, FrameDescriptor
from treehornx.enum_labels.core.Label import Label, LabelFactory
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
    parent: str | None = None
    k: int = field(init=False)
    db: StatesDB = field(init=False, default_factory=StatesDB)
    label_factory: LabelFactory = field(init=False, default_factory=LabelFactory)
    backbone_label_filter: Callable[[Label, bool], bool] = lambda l, b: True
    backbone_pair_filter: Callable[[tuple[Label, Label, str|int], bool], bool] = lambda p, b: True

    def __post_init__(self):
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        self.k = len(self._named_children_keys)

    @cached_property
    def _pointers(self) -> tuple[Var, ...]:
        return tuple(p for p in self.function.vars if p.sort.is_ptr())

    @cached_property
    def _named_children_keys(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.root.sort.pointee.fields.values() if p.sort.is_ptr() and p.name != self.parent)

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
        assert all(v.sort.is_enum() for v in vars)
        values: Iterable[tuple[str, ...]] = (tuple(var.sort.flags.keys()) for var in vars)  # type: ignore
        for prod in product(*values):
            yield frozendict({var.name: val for var, val in zip(vars, prod)})

    def active_child_products(self) -> Iterable[frozendict[str | int, bool]]:
        for bits in product([True, False], repeat=len(self._named_children_keys)):
            yield frozendict(
                chain(zip(self._named_children_keys, bits), ((i, False) for i in self._indexed_children_keys))
            )

    def backbone_labels(self) -> Iterable[Label]:
        logger.debug("backbone_labels: start")
        upd: frozendict[str, bool] = frozendict({p.name: False for p in self._pointers})
        isnil: frozendict[str, bool] = frozendict({p.name: True for p in self._pointers})

        # enum_values_product = self.enums_products(self.enum_vars())
        enum_fields_product = list(self.enums_products(self._enum_fields))
        # for enum_values, enum_fields in product(enum_values_product, enum_fields_product):
        enum_values: frozendict[str, str] = frozendict({v.name: tuple(v.sort.flags)[0] for v in self._enum_vars})
        #enum_fields: frozendict[str, str] = frozendict({f.name: tuple(f.sort.flags)[0] for f in self._enum_fields})
        count = 0
        for active_child, enum_fields in product(self.active_child_products(), enum_fields_product):
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
            lab = self.label_factory.create(active_frame, None)
            self.db.add_label(lab)
            if self.backbone_label_filter(lab, False):
                count += 1
                yield lab
        for enum_fields in enum_fields_product:
            inactive_frame = Frame(
                index=0,
                active=False,
                pc=0,
                upd=upd,
                isnil=isnil,
                events=frozenset(),
                active_child=frozendict(chain(((key, False) for key in self._named_children_keys), ((key, True) for key in self._indexed_children_keys))),
                enum_vars=enum_values,
                enum_fields=enum_fields,
                prev=None,
            )
            lab = self.label_factory.create(inactive_frame, None)
            self.db.add_label(lab)
            if self.backbone_label_filter(lab, False):
                count += 1
                yield lab
        logger.debug(f"backbone_labels: done, yielded {count} labels")

    def start_labels(self) -> Iterable[Label]:
        logger.debug("start_labels: begin")
        count = 0
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
            lab = self.label_factory.create(second_frame, backbone_label)
            self.db.add_label(lab)
            assert lab.origin
            if self.backbone_label_filter(lab.origin, True):
                count += 1
                yield lab
        logger.debug(f"start_labels: done, yielded {count} labels")

    def initial_root_pairs(self) -> Iterable[Pair]:
        logger.debug("initial_root_pairs: begin")
        count = 0
        for parent, child, child_key in product(self.start_labels(), self.backbone_labels(), self._children_keys):
            # parent_active = parent[1].active_child.get("parent", False)
            if (
                parent[1].active_child[child_key] == child[0].active and
                (isinstance(child_key, str) or not child[0].active) and
                self.backbone_pair_filter((parent, child, child_key), True)
            ):  # and not parent_active:
                pair = Pair(parent=parent, child=child, child_key=child_key)
                count += 1
                yield pair
        logger.debug(f"initial_root_pairs: done, yielded {count} pairs")

    def initial_internal_node_pairs(self) -> Iterable[Pair]:
        logger.debug("initial_internal_node_pairs: begin")
        count = 0
        # assert "parent" not in self._children_keys
        for parent, child, child_key in product(self.backbone_labels(), self.backbone_labels(), self._children_keys):
            # parent_active = parent[0].active_child.get("parent", False)
            if (
                parent[0].active and
                parent[0].active_child[child_key] == child[0].active and
                (isinstance(child_key, str) or not child[0].active) and
                self.backbone_pair_filter((parent, child, child_key), False)
            ):
                pair = Pair(parent=parent, child=child, child_key=child_key)
                count += 1
                yield pair
        logger.debug(f"initial_internal_node_pairs: done, yielded {count} pairs")

    def _add_ancestor(self, label: Label, ancestor: Label) -> None:
        self.db.add_ancestor(label, ancestor)

    def _add_pair(self, pair: Pair) -> None:
        self.db.add_pair(pair)
        self.db.add_label(pair.leader())
        self.db.add_label(pair.follower())

    def _initialize_pairs(self):
        logger.debug("_initialize_pairs: begin")
        root_count = 0
        for pair in self.initial_root_pairs():
            self._add_pair(pair)
            root_count += 1
        logger.debug(f"_initialize_pairs: added {root_count} root pairs")
        internal_count = 0
        for pair in self.initial_internal_node_pairs():
            self._add_pair(pair)
            internal_count += 1
        logger.debug(f"_initialize_pairs: added {internal_count} internal pairs, total labels={self.db.labels_count()}, total pairs={self.db.pairs_count()}")

    def _make_knitter(self) -> IKnitter:
        def make_label(o: Label | None, f: Frame) -> Label:
            lab = self.label_factory.create(f, o)
            self.db.add_label(lab)
            return lab

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
                parent=self.parent
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
                parent=self.parent
            )

        return knitter

    def generate(self):
        logger.debug("generate: begin — collecting initial root pairs for queue")
        initial_root = list(self.initial_root_pairs())
        queue: deque[Pair] = deque(initial_root)
        logger.debug(f"generate: initial queue size = {len(initial_root)}")

        self._initialize_pairs()
        logger.debug(f"generate: after _initialize_pairs — labels={self.db.labels_count()}, pairs={self.db.pairs_count()}")

        knitter = self._make_knitter()

        knit_call_count = 0
        knit_cache_hits = 0

        @cache
        def knit(pair: Pair) -> KnitResult:
            nonlocal knit_call_count
            knit_call_count += 1
            return knitter.knit(pair)

        def is_continuos_pair(pair: Pair) -> bool:
            nonlocal knit_cache_hits
            info = knit.cache_info()
            result = knit(pair)
            if knit.cache_info().hits > info.hits:
                knit_cache_hits += 1
            return result != StepFailed()

        def qappend(pair: Pair):
            queue.append(pair)

        processed: set[Pair] = set()
        step_failed_count = 0
        internal_step_count = 0
        external_step_count = 0
        skip_pivot_count = 0
        skip_processed_count = 0
        log_interval = 500

        while queue:
            pair = queue.popleft()

            if self.db.is_endless_loop_pivot(pair.leader()):
                skip_pivot_count += 1
                continue

            if pair in processed:
                skip_processed_count += 1
                continue

            processed.add(pair)

            total_processed = len(processed)
            if total_processed % log_interval == 0:
                cache_info = knit.cache_info()
                logger.debug(
                    f"generate: processed={total_processed}, queue={len(queue)}, "
                    f"labels={self.db.labels_count()}, pairs={self.db.pairs_count()}, "
                    f"knit_calls={knit_call_count}, cache_hits={cache_info.hits}, cache_misses={cache_info.misses}, "
                    f"step_failed={step_failed_count}, internal={internal_step_count}, external={external_step_count}, "
                    f"skip_pivot={skip_pivot_count}, skip_processed={skip_processed_count}"
                )

            knit_result = knit(pair)

            match knit_result:
                case StepFailed():  # non continuos pair
                    step_failed_count += 1
                    for extended_leader in self.db.get_connection_extensions(pair.leader()):
                        new_pair = pair.replace_leader(extended_leader)
                        self._add_pair(new_pair)
                        qappend(new_pair)
                case InternalStepResult(chain_end_pairs):  # internal steps
                    internal_step_count += 1
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
                case ExternalStepResult(pair=Pair(parent, child, child_key, leadership)):
                    external_step_count += 1
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

        cache_info = knit.cache_info()
        logger.debug(
            f"generate: done — processed={len(processed)}, "
            f"labels={self.db.labels_count()}, pairs={self.db.pairs_count()}, "
            f"knit_calls={knit_call_count}, cache_hits={cache_info.hits}, cache_misses={cache_info.misses}, "
            f"step_failed={step_failed_count}, internal={internal_step_count}, external={external_step_count}, "
            f"skip_pivot={skip_pivot_count}, skip_processed={skip_processed_count}"
        )
