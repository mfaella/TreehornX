import json
import sys
from asyncio.unix_events import SelectorEventLoop
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from functools import cache, cached_property
from itertools import chain, count, product
from typing import Iterable

from frozendict import frozendict
from loguru import logger

from treehornx.chc.knitter.IKnitter import IKnitter
from treehornx.chc.knitter.KnitResult import ExternalStepResult, InternalStepResult, KnitResult, StepFailed
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.ir.instructions import *
from treehornx.ir.sorts import Enum, Pointer, Struct

from .core import Frame, FrameDescriptor, Label
from .core.Dir import Down, Internal, Up
from .core.Event import ERR, LOF, NOP, OOM, Here, Loop
from .knitter.CompressedBoundedInternalChainKnitter import CompressedBoundedInternalChainKnitter
from .knitter.CompressedUnboundedInternalChainKnitter import CompressedUnboundedInternalChainKnitter
from .knitter.Pair import LeadershipKind, Pair
from .LabelDB import LabelDB
from .PairDB import PairDB
from .SMT2FileBuilder import SMT2FileBuilder

# logger.remove(0)
# logger.add(sys.stdout, level=20)


@dataclass
class LabelInfo:
    id: int
    ancestors: set[Label] = field(init=False, default_factory=set)
    extensions: set[Label] = field(init=False, default_factory=set)


@dataclass
class FixPointEnumLabelGenerator:
    function: Function
    root: Var
    m: int
    n: int
    internal_chain_bound: int | None = None
    k: int = field(init=False)
    pairs: PairDB = field(init=False, default_factory=PairDB)
    labels: LabelDB = field(init=False, default_factory=LabelDB)

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
        enum_values = frozendict({v.name: tuple(v.sort.flags)[0] for v in self._enum_vars})
        enum_fields = frozendict({f.name: tuple(f.sort.flags)[0] for f in self._enum_fields})
        for active_child in self.active_child_products():
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
            yield self.labels.make(None, active_frame)
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
        yield self.labels.make(None, inactive_frame)

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
            yield self.labels.make(backbone_label, second_frame)

    def initial_root_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.start_labels(), self.backbone_labels(), self._children_keys):
            # parent_active = parent[1].active_child.get("parent", False)
            if parent[1].active_child[child_key] == child[0].active:  # and not parent_active:
                pair = Pair(parent=parent, child=child, child_key=child_key)
                yield pair

    def initial_internal_node_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.backbone_labels(), self.backbone_labels(), self._children_keys):
            if parent[1].active_child[child_key] == child[0].active:
                pair = Pair(parent=parent, child=child, child_key=child_key)
                yield pair

    def _add_ancestor(self, label: Label, ancestor: Label) -> None:
        self.labels.add_ancestor(label, ancestor)

    def _add_pair(self, pair: Pair) -> None:
        self.pairs.add(pair)
        self.labels.add(pair.leader())
        self.labels.add(pair.follower())

    # def add_internal_step_dependency(self, label: Label):
    #     for ancestor in self.labels_db.find_ancestors(label):
    #         pc = label.frame.pc
    #         instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
    #         self.add_label_node(self.dependency_graph, ancestor)
    #         self.add_label_node(self.dependency_graph, label)
    #         self.dependency_graph.edge(ancestor.name, label.name, label="I", color="blue")

    # def add_external_step_dependency(self, pair: Pair):
    #     sigma = pair.follower()
    #     tau = pair.leader()
    #     if sigma == tau:
    #         logger.debug(f"adding self dependency for label {sigma.id}")
    #     if self.create_dependency_graph:
    #         self.add_label_node(self.dependency_graph, tau)
    #         external_step_label = f"{f'D({pair.child_key})' if pair.dir() == Up() else 'U'}"
    #         self.dependency_graph.edge(sigma.name, tau.name, label=external_step_label, color="blue")
    #         for ancestor in self.labels_db.find_ancestors(tau):
    #             self.dependency_graph.edge(ancestor.name, tau.name, label="I", color="grey")
    #         if tau.frame.prev is not None and tau.frame.prev[0] != Internal():
    #             self.dependency_graph.edge(tau.origin.name, tau.name, label="I", color="grey")

    # def build_dep_graph(self):
    #     if self.dependency_graph is None:
    #         return

    #     self.dependency_graph.attr(bgcolor="lightgrey", style="filled")

    #     pairs = {
    #         p
    #         for p in self.db.pairs_db
    #         if p.leader().frame.prev is not None
    #         and (p.leader().frame.prev[0] == Internal() or p.leader().frame.prev[0] == p.dir())
    #     }
    #     default_pairs = {*self.initial_root_pairs(), *self.initial_internal_node_pairs()}
    #     pairs.difference_update(default_pairs)
    #     for pair in pairs:
    #         leader = pair.leader()
    #         follower = pair.follower()
    #         if leader.frame.prev is not None and leader.frame.prev[0] == Internal():
    #             self.add_internal_step_dependency(leader)
    #         elif leader.frame.prev is not None and follower.frame.index != 0:
    #             self.add_external_step_dependency(pair)

    # def add_label_node(self, graph: gv.Digraph, lab: Label):
    #     f = lab.frame
    #     fjson = {
    #         "index": f.index,
    #         "active": f.active,
    #         "pc": f.pc,
    #         "upd": dict(f.upd),
    #         "isnil": dict(f.isnil),
    #         "event": list(str(e) for e in f.events),
    #         "active_child": dict(f.active_child),
    #         "enum_values": dict(f.enum_vars),
    #         "enum_fields": dict(f.enum_fields),
    #         "prev": None if f.prev is None else (str(f.prev[0]), f.prev[1]),
    #     }
    #     tooltip = json.dumps(fjson, indent=2)

    #     if Loop() in lab.frame.events:
    #         graph.node(lab.name, style="filled", tooltip=tooltip, label=f"Loop()", fillcolor="red")
    #         return

    #     err_event = next((e for e in lab.frame.events if e in {ERR(), OOM(), LOF()}), None)
    #     if err_event:
    #         graph.node(lab.name, tooltip=tooltip, style="filled", label=f"{lab.name}:{err_event}", fillcolor="yellow")
    #         return

    #     if Exit() in lab.frame.events:
    #         graph.node(lab.name, tooltip=tooltip, style="filled", label=f"{lab.name}:Exit()", fillcolor="lightgreen")
    #         return

    #     if lab.origin is None:
    #         graph.node(lab.name, label=f"{lab.name}", tooltip=tooltip, style="filled", fillcolor="white")
    #     else:
    #         pc = lab.frame.pc
    #         instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
    #         graph.node(lab.name, label=f"{lab.name}\n{instr}", tooltip=tooltip, style="filled", fillcolor="white")

    # def build_consecutive_internal_dep_graph(self, path):
    #     consecutive_dep_graph = gv.Digraph("consecutive internal dependency graph", strict=True)
    #     consecutive_dep_graph.attr(bgcolor="lightgrey", style="filled")
    #     prevs = defaultdict(set)
    #     nexts = defaultdict(set)

    #     for label in self.labels_db.labels():
    #         if label.origin is None or label.frame.prev is None:
    #             continue

    #         self.add_label_node(consecutive_dep_graph, label)
    #         if label.frame.prev[0] != Internal():
    #             self.add_label_node(consecutive_dep_graph, label.origin)
    #             consecutive_dep_graph.edge(label.origin.name, label.name, label="I", color="grey")
    #             label_prevs: set[Label] = {
    #                 p.follower() for p in self.db.find_by_leader(label) if p.dir() == label.frame.prev[0]
    #             }
    #             prevs[label] = label_prevs
    #             for prev in label_prevs:
    #                 nexts[prev].add(label)
    #             # dir = next(iter(prevs)).rev_dir()
    #             # prev_text = "\n".join(map(lambda p: p.follower().name, prevs))
    #             # consecutive_dep_graph.node(f"{label.name}.prevs", label=prev_text, style="filled", fillcolor="white")
    #             # consecutive_dep_graph.edge(f"{label.name}.prevs", label.name, label=str(dir), color="blue")

    #             # if label.frame.index > 1:
    #             #     nexts = {p for p}
    #         else:
    #             for ancestor in self.labels_db.find_ancestors(label):
    #                 self.add_label_node(consecutive_dep_graph, ancestor)
    #                 consecutive_dep_graph.edge(ancestor.name, label.name, label="I", color="blue")

    #         for lab, prev_labs in prevs.items():
    #             dir = next(p for p in self.db.find_by_leader(lab) if p.dir() == lab.frame.prev[0]).rev_dir()
    #             prev_text = "\n".join(map(lambda l: l.name, prev_labs))
    #             consecutive_dep_graph.node(f"{lab.name}.prevs", label=prev_text, style="filled", fillcolor="white")
    #             consecutive_dep_graph.edge(f"{lab.name}.prevs", lab.name, color="blue")

    #         for lab, next_labs in nexts.items():
    #             next_text = "\n".join(map(lambda l: l.name, next_labs))
    #             consecutive_dep_graph.node(f"{lab.name}.nexts", label=next_text, style="filled", fillcolor="white")
    #             consecutive_dep_graph.edge(lab.name, f"{lab.name}.nexts", color="blue")

    #             # if label.frame.index > 1:
    #             #     nexts = {p for p}
    #     consecutive_dep_graph.save(path)

    # def build_pairs_text_file(self):
    #     pairs = {
    #         p
    #         for p in self.db.pairs_db
    #         if p.leader().frame.prev is not None
    #         and (p.leader().frame.prev[0] == Internal() or p.leader().frame.prev[0] == p.dir())
    #     }
    #     default_pairs = {*self.initial_root_pairs(), *self.initial_internal_node_pairs()}
    #     pairs.difference_update(default_pairs)
    #     text_pairs: set[tuple[int, int, StepKind]] = set()
    #     for pair in pairs:
    #         leader = pair.leader()
    #         follower = pair.follower()
    #         if leader.frame.prev is not None and leader.frame.prev[0] == Internal():
    #             for ancestor in self.labels_db.find_ancestors(leader):
    #                 sigma_id = ancestor.id
    #                 tau_id = leader.id
    #                 text_pairs.add((sigma_id, tau_id, StepKind.INTERNAL))

    #         elif leader.frame.prev is not None and follower.frame.index != 0:
    #             sigma_id = follower.id
    #             tau_id = leader.id
    #             text_pairs.add((sigma_id, tau_id, StepKind.EXTERNAL))
    #     with open(f"report/{self.function.name}_pairs.csv", "w") as pairs_txt:
    #         pairs_txt.write("sigma,tau,kind\n")
    #         for p in text_pairs:
    #             kind = "internal" if p[2] == StepKind.INTERNAL else "external"
    #             pairs_txt.write(f"{p[0]},{p[1]},{kind}\n")

    def _initialize_pairs(self):
        for pair in self.initial_root_pairs():
            self._add_pair(pair)
        for pair in self.initial_internal_node_pairs():
            self._add_pair(pair)

    def _make_knitter(self) -> IKnitter:
        def make_label(o: Label | None, f: Frame) -> Label:
            return self.labels.make(o, f)

        def on_new_internal_step(ancestor_pair: Pair, lab_pair: Pair):
            self._add_ancestor(lab_pair.leader(), ancestor_pair.leader())
            self._add_pair(lab_pair)

        def on_new_external_step(previous_pair: Pair, lab_pair: Pair):
            self._add_pair(lab_pair)

        if self.internal_chain_bound is None:

            def on_endless_loop_detected(pivot: Pair):
                self.labels.set_endless_loop_pivot(pivot.leader())

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
            if is_continuos_pair(pair):
                queue.append(pair)

        processed: set[Pair] = set()

        while queue:
            pair = queue.popleft()

            if Loop() in pair.leader().frame.events:
                continue

            if pair in processed:
                continue

            processed.add(pair)

            knit_result = knit(pair)

            match knit_result:
                case StepFailed():  # non continuos pair
                    for extended_leader in self.labels.find_by_origin(pair.leader()):
                        new_pair = pair.replace_leader(extended_leader)
                        self._add_pair(new_pair)
                        qappend(new_pair)
                case InternalStepResult(chain_end_pairs):  # internal steps
                    for chain_end_pair in chain_end_pairs:
                        new_leader = chain_end_pair.leader()
                        assert pair in set(self.pairs.find_by_leader(pair.leader()))
                        for p in self.pairs.find_by_leader(pair.leader()):
                            parent = new_leader if p.leadership == LeadershipKind.PARENT else p.parent
                            child = new_leader if p.leadership == LeadershipKind.CHILD else p.child
                            leadership = p.leadership
                            child_key = p.child_key
                            new_p = Pair(parent, child, child_key, leadership)
                            qappend(new_p)
                            self._add_pair(new_p)
                case ExternalStepResult(pair=Pair(parent, child, child_key, leadership)):
                    self._add_pair(pair)
                    qappend(pair)

                    new_leader = parent if leadership == LeadershipKind.PARENT else child
                    for p in self.pairs.find_by_leader(
                        pair.follower()
                    ):  # finding by follower because the leadership has been switched in the new pair
                        if (leadership != p.leadership or child_key != p.child_key) and not is_continuos_pair(p):
                            parent = new_leader if p.leadership == LeadershipKind.PARENT else p.parent
                            child = new_leader if p.leadership == LeadershipKind.CHILD else p.child
                            leadership = p.leadership
                            child_key = p.child_key
                            new_p = Pair(parent, child, child_key, leadership)
                            self._add_pair(new_p)
                            qappend(new_p)

        # logger.info("All pair have been generated")
        # assert len(queue) == 0
        # logger.info("Building dependency graph")
        # self.build_dep_graph()
        # self.dependency_graph.save(f"report/{self.function.name}.dot")
        # self.build_consecutive_internal_dep_graph(f"report/{self.function.name}_internals.dot")
        # self.build_pairs_text_file()

        # pppsss = sorted((p.parent.id, p.child.id) for p in self.db.pairs_db)
        # for p in pppsss:
        #     logger.info(f"PAIR {p}")

    # def makeSMT2FileBuilder(self) -> SMT2FileBuilder:
    #     smt2file = SMT2FileBuilder(
    #         {v for v in self.function.vars if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},
    #         {v for v in self.root.sort.pointee.fields.values() if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},  # type: ignore
    #     )
    #     for lab in self.start_frames():
    #         smt2file.assert_fact(Label.make(*lab))
    #     for lab in self.first_frames():
    #         smt2file.assert_fact(Label.make(lab))

    #     def is_lace_step(pair: Pair) -> bool:
    #         if pair.leader().frame.prev[0] == Internal():
    #             return True
    #         return pair.leader().frame.prev[0] == pair.dir()

    #     lace_step_pairs = self.pairs.pairs_db.difference(
    #         {*self.initial_root_pairs(), *self.initial_internal_node_pairs()}
    #     )
    #     lace_step_pairs = set(p for p in lace_step_pairs if is_lace_step(p))

    #     for pair in lace_step_pairs:
    #         if pair.leader().frame.prev[0] == Internal():
    #             for ancestor in self.labels_db.find_ancestors(pair.leader()):
    #                 if ancestor.frame.pc >= len(self.function.instructions):
    #                     continue
    #                 inst = self.function.instructions[ancestor.frame.pc]
    #                 smt2file.assert_internal_step(pair.leader(), ancestor, inst)
    #         else:
    #             smt2file.assert_external_step(pair)
    #     return smt2file
