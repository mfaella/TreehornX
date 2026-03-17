import json
import sys
from asyncio.unix_events import SelectorEventLoop
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from functools import cache, cached_property
from itertools import chain, count, product
from typing import Iterable

import graphviz as gv
from frozendict import frozendict
from loguru import logger

from treehornx.chc.core.dir import Up
from treehornx.chc.core.pair import LeadershipKind
from treehornx.ir.expressions import Not, Var
from treehornx.ir.function import Function
from treehornx.ir.instructions import *
from treehornx.ir.sorts import Enum, Pointer, Struct

from .core import Frame, FrameDescriptor, Label, Pair
from .core.dir import Down, Internal
from .core.event import ERR, LOF, NOP, OOM, Exit, Here, Loop
from .Knitter import Knitter, StepKind
from .LabelDB import LabelDB
from .PairDB import PairDB
from .SMT2FileBuilder import SMT2FileBuilder

# logger.remove(0)
# logger.add(sys.stdout, level=20)


@dataclass
class ChcGenerator:
    function: Function
    root: Var
    m: int
    n: int
    create_dependency_graph: bool = True
    k: int = field(init=False)
    db: PairDB = field(init=False, default_factory=PairDB)
    labels_db: LabelDB = field(init=False, default_factory=LabelDB)
    dependency_graph: gv.Digraph | None = field(init=False, default=None)

    def __post_init__(self):
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        self.k = sum(1 for f in root_sort.fields.values() if f.sort.is_ptr())

        if self.create_dependency_graph:
            self.dependency_graph = gv.Digraph("dependency graph", strict=True)

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

        # enum_values_product = self.enums_products(self.enum_vars())
        # enum_fields_product = self.enums_products(self.enum_fields())
        # for enum_values, enum_fields in product(enum_values_product, enum_fields_product):
        enum_values = frozendict({v.name: list(v.sort.flags)[0] for v in self.enum_vars()})
        enum_fields = frozendict({f.name: list(f.sort.flags)[0] for f in self.enum_fields()})
        for active_child in self.active_child_products():
            active_frame = Frame(
                index=0,
                active=True,
                pc=0,
                upd=upd,
                isnil=isnil,
                events=frozenset(),
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
            events=frozenset(),
            active_child=frozendict({key: True for key in self.children_keys}),
            enum_values=enum_values,
            enum_fields=enum_fields,
            prev=None,
        )
        yield inactive_frame

    def start_frames(self) -> Iterable[tuple[Frame, Frame]]:
        for first_frame in self.first_frames():
            frame_builder = FrameDescriptor()
            frame_builder.index = 1
            frame_builder.active = first_frame.active
            frame_builder.prev = (Internal(), 1)
            if frame_builder.active:
                frame_builder.event = Here(self.root.name)
                frame_builder.isnil[self.root.name] = False
            else:
                frame_builder.event = NOP()
                frame_builder.active_child = {key: False for key in self.children_keys}
            second_frame = Frame(
                index=1,
                active=first_frame.active,
                pc=0,
                upd=frozendict({key.name: False for key in self.pointers}),
                isnil=frozendict(
                    {key.name: key.name != self.root.name for key in self.pointers}
                    if first_frame.active
                    else {key.name: True for key in self.pointers}
                ),
                events=frozenset({Here(self.root.name)}) if first_frame.active else frozenset(),
                enum_fields=first_frame.enum_fields,
                enum_values=first_frame.enum_values,
                active_child=first_frame.active_child
                if first_frame.active
                else frozendict({key: False for key in self.children_keys}),
                prev=(Internal(), 1),
            )
            yield first_frame, second_frame

    def start_pairs(self) -> Iterable[Pair]:
        for parent, child, child_key in product(self.start_frames(), self.first_frames(), self.children_keys):
            parent_active = parent[1].active_child.get("parent", False)
            if parent[1].active_child[child_key] == child.active and not parent_active:
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

    def _add_ancestor(self, label: Label, ancestor: Label) -> None:
        self.labels_db.add_ancestor(label, ancestor)

    def _add_label(self, label: Label) -> None:
        self.labels_db.add(label)

    def _add_pair(self, pair: Pair) -> None:
        self.db.add(pair)
        self._add_label(pair.leader())
        self._add_label(pair.follower())

    def add_internal_step_dependency(self, label: Label):
        for ancestor in self.labels_db.find_ancestors(label):
            pc = label.frame.pc
            instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
            self.add_label_node(self.dependency_graph, ancestor)
            self.add_label_node(self.dependency_graph, label)
            self.dependency_graph.edge(ancestor.name, label.name, label="I", color="blue")

    def add_external_step_dependency(self, pair: Pair):
        sigma = pair.follower()
        tau = pair.leader()
        if sigma == tau:
            logger.debug(f"adding self dependency for label {sigma.id}")
        if self.create_dependency_graph:
            self.add_label_node(self.dependency_graph, tau)
            external_step_label = f"{f'D({pair.child_key})' if pair.dir() == Up() else 'U'}"
            self.dependency_graph.edge(sigma.name, tau.name, label=external_step_label, color="blue")
            for ancestor in self.labels_db.find_ancestors(tau):
                self.dependency_graph.edge(ancestor.name, tau.name, label="I", color="grey")
            if tau.frame.prev is not None and tau.frame.prev[0] != Internal():
                self.dependency_graph.edge(tau.origin.name, tau.name, label="I", color="grey")

    def build_dep_graph(self):
        if self.dependency_graph is None:
            return

        self.dependency_graph.attr(bgcolor="lightgrey", style="filled")

        pairs = {
            p
            for p in self.db.pairs_db
            if p.leader().frame.prev is not None
            and (p.leader().frame.prev[0] == Internal() or p.leader().frame.prev[0] == p.dir())
        }
        default_pairs = {*self.start_pairs(), *self.first_pairs()}
        pairs.difference_update(default_pairs)
        for pair in pairs:
            leader = pair.leader()
            follower = pair.follower()
            if leader.frame.prev is not None and leader.frame.prev[0] == Internal():
                self.add_internal_step_dependency(leader)
            elif leader.frame.prev is not None and follower.frame.index != 0:
                self.add_external_step_dependency(pair)

    def add_label_node(self, graph: gv.Digraph, lab: Label):
        if Loop() in lab.frame.events:
            graph.node(lab.name, style="filled", label=f"Loop()", fillcolor="red")
            return

        err_event = next((e for e in lab.frame.events if e in {ERR(), OOM(), LOF()}), None)
        if err_event:
            graph.node(lab.name, style="filled", label=f"{lab.name}:{err_event}", fillcolor="yellow")
            return

        if Exit() in lab.frame.events:
            graph.node(lab.name, style="filled", label=f"{lab.name}:Exit()", fillcolor="lightgreen")
            return

        f = lab.frame
        fjson = {
            "index": f.index,
            "active": f.active,
            "pc": f.pc,
            "upd": dict(f.upd),
            "isnil": dict(f.isnil),
            "event": list(str(e) for e in f.events),
            "active_child": dict(f.active_child),
            "enum_values": dict(f.enum_values),
            "enum_fields": dict(f.enum_fields),
            "prev": None if f.prev is None else (str(f.prev[0]), f.prev[1]),
        }
        tooltip = json.dumps(fjson, indent=2)
        if lab.origin is None:
            graph.node(lab.name, label=f"{lab.name}", tooltip=tooltip, style="filled", fillcolor="white")
        else:
            pc = lab.frame.pc
            instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
            graph.node(lab.name, label=f"{lab.name}\n{instr}", tooltip=tooltip, style="filled", fillcolor="white")

    def build_consecutive_internal_dep_graph(self, path):
        consecutive_dep_graph = gv.Digraph("consecutive internal dependency graph", strict=True)
        consecutive_dep_graph.attr(bgcolor="lightgrey", style="filled")

        for label in self.labels_db.labels():
            if label.origin is None or label.frame.prev is None:
                continue

            self.add_label_node(consecutive_dep_graph, label)
            if label.frame.prev[0] != Internal():
                self.add_label_node(consecutive_dep_graph, label.origin)
                consecutive_dep_graph.edge(label.origin.name, label.name, label=str(label.frame.prev[0]), color="red")
            else:
                for ancestor in self.labels_db.find_ancestors(label):
                    self.add_label_node(consecutive_dep_graph, ancestor)
                    consecutive_dep_graph.edge(ancestor.name, label.name, label="I", color="black")
        consecutive_dep_graph.save(path)

    def generate(self):
        queue: deque[Pair] = deque()

        for pair in self.start_pairs():
            self._add_pair(pair)
            queue.append(pair)

        for pair in self.first_pairs():
            self._add_pair(pair)

        knitter = Knitter(self.function, self.k, self.m, self.n)

        def last_step_kind(pair: Pair) -> StepKind:
            last_frame = pair.leader().frame
            if last_frame.prev[0] == Internal():
                return StepKind.INTERNAL
            else:
                return StepKind.EXTERNAL

        def knit_internal_steps_chain(pair: Pair) -> tuple[Pair, ...]:
            final_pairs: list[Pair] = []
            visited_internal_step: set[tuple[Label, Label]] = set()
            q: deque[Pair] = deque()

            def handle(p: Pair, p_: Pair):
                if (p.leader(), p_.leader()) in visited_internal_step:
                    p__leader_last_frame = p_.leader().frame
                    p__leader_new_last_frame = replace(
                        p__leader_last_frame, events=p__leader_last_frame.events.union({Loop()})
                    )
                    p__new_leader = p_.leader().origin.extended_with(p__leader_new_last_frame)
                    self._add_ancestor(p__new_leader, p.leader())
                    if p_.leadership == LeadershipKind.PARENT:
                        p_ = replace(p_, parent=p__new_leader)
                    else:
                        p_ = replace(p_, child=p__new_leader)
                    self._add_pair(p_)
                else:
                    visited_internal_step.add((p.leader(), p_.leader()))
                    self._add_pair(p_)
                    self._add_ancestor(p_.leader(), p.leader())
                    q.append(p_)

            q.append(pair)
            while q:
                p = q.popleft()

                knit_result = knitter.knit(p)
                if knit_result is None:
                    final_pairs.append(p)
                    continue

                p1, p2 = knit_result
                if last_step_kind(p1) == StepKind.INTERNAL:
                    handle(p, p1)

                    if p2 is None:
                        continue

                    handle(p, p2)

                else:
                    final_pairs.append(p)

            return tuple(final_pairs)

        @cache
        def knit(pair: Pair) -> tuple[Pair, ...] | Pair | None:
            """returns
            None if pair is not a continuity pair
            a tuple of pairs if the pair generates some internal step chains
            a pair if it just process an external step
            """
            knit_result = knitter.knit(pair)
            if knit_result is None:
                return None
            elif last_step_kind(knit_result[0]) == StepKind.INTERNAL:
                return knit_internal_steps_chain(pair)
            else:
                return knit_result[0]

        def is_continuos_pair(pair: Pair) -> bool:
            return knit(pair) is not None

        def qappend(pair: Pair):
            if is_continuos_pair(pair):
                queue.append(pair)

        # def update_after_internal_connection_frame_discovered(last_label: Label, enqueue: bool = False):
        #     # already_updated_pairs = connected_pairs_index[last_label.origin]
        #     # connected_pairs = set(self.db.find_by_leader(leader=last_label.origin))
        #     # pairs = connected_pairs.difference(already_updated_pairs)
        #     # connected_pairs_index[last_label.origin] = connected_pairs
        #     pairs = set(self.db.find_by_leader(leader=last_label.origin))
        #     for p in pairs:
        #         parent = last_label if p.leadership == LeadershipKind.PARENT else p.parent
        #         child = last_label if p.leadership == LeadershipKind.CHILD else p.child
        #         child_key = p.child_key
        #         leadership = p.leadership
        #         new_p = Pair(parent=parent, child=child, child_key=child_key, leadership=leadership)
        #         self._add_pair(new_p)
        #         if enqueue:
        #             qappend(new_p)

        # def update_after_external_connection_frame_discovered(new_pair: Pair, enqueue: bool = False):
        #     pairs = set(self.db.find_by_leader(leader=new_pair.leader().origin))
        #     for p in pairs:
        #         if new_pair.leadership != p.leadership or new_pair.child_key != p.child_key:
        #             parent = new_pair1.follower() if p.leadership == LeadershipKind.PARENT else p.parent
        #             child = new_pair1.follower() if p.leadership == LeadershipKind.CHILD else p.child
        #             child_key = p.child_key
        #             leadership = p.leadership
        #             new_p = Pair(parent=parent, child=child, child_key=child_key, leadership=leadership)
        #             self._add_pair(new_p)
        #             if enqueue:
        #                 qappend(new_p)

        # def update_with_discovered_connection_frames(pair: Pair, enqueue: bool = False):
        #     """when the internal steps of a label has already been processed,
        #     this function just adds it to the leader the keep processing"""
        #     for lab in self.labels_db.find_by_origin(pair.leader()):
        #         parent = lab if pair.leadership == LeadershipKind.PARENT else pair.parent
        #         child = lab if pair.leadership == LeadershipKind.CHILD else pair.child
        #         child_key = pair.child_key
        #         leadership = pair.leadership
        #         new_p = Pair(parent=parent, child=child, child_key=child_key, leadership=leadership)
        #         self._add_pair(new_p)
        #         if enqueue:
        #             qappend(new_p)

        processed: set[Pair] = set()

        while queue:
            pair = queue.popleft()
            logger.info(
                f"extracted from queue: {{parent={pair.parent.id}, child={pair.child.id}, child_key={pair.child_key}, leadership={pair.leadership}}}"
            )

            if Loop() in pair.leader().frame.events:
                continue

            if pair in processed:
                continue

            processed.add(pair)

            knit_result = knit(pair)

            match knit_result:
                case None:  # non continuos pair
                    for extended_leader in self.labels_db.find_by_origin(pair.leader()):
                        new_pair = pair.updated_with_leader(extended_leader)
                        self._add_pair(new_pair)
                        qappend(new_pair)
                case tuple():  # internal steps
                    for chain_end_label in knit_result:
                        new_leader = chain_end_label.leader()
                        assert pair in set(self.db.find_by_leader(pair.leader()))
                        for p in self.db.find_by_leader(pair.leader()):
                            parent = new_leader if p.leadership == LeadershipKind.PARENT else p.parent
                            child = new_leader if p.leadership == LeadershipKind.CHILD else p.child
                            leadership = p.leadership
                            child_key = p.child_key
                            new_p = Pair(parent, child, child_key, leadership)
                            qappend(new_p)
                            self._add_pair(new_p)
                case Pair(parent, child, child_key, leadership):  # external step
                    self._add_pair(knit_result)
                    qappend(knit_result)

                    new_leader = parent if leadership == LeadershipKind.PARENT else child
                    for p in self.db.find_by_leader(
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

        logger.info("All pair have been generated")
        assert len(queue) == 0
        logger.info("Building dependency graph")
        self.build_dep_graph()
        self.dependency_graph.save(f"report/{self.function.name}.dot")
        self.build_consecutive_internal_dep_graph(f"report/{self.function.name}_internals.dot")

        # pppsss = sorted((p.parent.id, p.child.id) for p in self.db.pairs_db)
        # for p in pppsss:
        #     logger.info(f"PAIR {p}")

    def makeSMT2FileBuilder(self) -> SMT2FileBuilder:
        smt2file = SMT2FileBuilder(
            {v for v in self.function.vars if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},
            {v for v in self.root.sort.pointee.fields.values() if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},  # type: ignore
        )
        for lab in self.start_frames():
            smt2file.assert_fact(Label.make(*lab))
        for lab in self.first_frames():
            smt2file.assert_fact(Label.make(lab))

        def is_lace_step(pair: Pair) -> bool:
            if pair.leader().frame.prev[0] == Internal():
                return True
            return pair.leader().frame.prev[0] == pair.dir()

        lace_step_pairs = self.db.pairs_db.difference({*self.start_pairs(), *self.first_pairs()})
        lace_step_pairs = set(p for p in lace_step_pairs if is_lace_step(p))

        for pair in lace_step_pairs:
            if pair.leader().frame.prev[0] == Internal():
                for ancestor in self.labels_db.find_ancestors(pair.leader()):
                    if ancestor.frame.pc >= len(self.function.instructions):
                        continue
                    inst = self.function.instructions[ancestor.frame.pc]
                    smt2file.assert_internal_step(pair.leader(), ancestor, inst)
            else:
                smt2file.assert_external_step(pair)
        return smt2file
