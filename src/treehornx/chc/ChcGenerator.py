import json
import sys
from asyncio.unix_events import SelectorEventLoop
from collections import defaultdict, deque
from dataclasses import dataclass, field
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

from .core import Frame, FrameBuilder, Label, Pair
from .core.dir import Down, Internal
from .core.event import ERR, LOF, NOP, OOM, Exit, Here
from .LabelDB import LabelDB
from .PairDB import PairDB
from .SMT2FileBuilder import SMT2FileBuilder
from .Stepper import StepKind, Stepper

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
    _step_cache: dict[Pair, tuple[Frame, Frame | None, StepKind] | None] = field(init=False, default_factory=lambda: {})

    def __post_init__(self):
        assert isinstance(self.root.sort, Pointer)
        root_sort = self.root.sort.pointee
        assert isinstance(root_sort, Struct)
        self.k = sum(1 for f in root_sort.fields.values() if f.sort.is_ptr())
        self.stepper = Stepper(self.function, self.k, self.m, self.n)

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
            frame_builder = FrameBuilder(base=first_frame)
            frame_builder.index = 1
            frame_builder.active = first_frame.active
            frame_builder.prev = (Internal(), 1)
            assert all(first_frame.isnil.values())
            if frame_builder.active:
                frame_builder.events.add(Here(self.root.name))
                frame_builder.isnil[self.root.name] = False
            else:
                frame_builder.events = set()
                frame_builder.active_child = {key: False for key in self.children_keys}
            yield first_frame, frame_builder.build()

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

    def update_globals_after_internal_step(self, pair: Pair, frame: Frame) -> Iterable[Pair]:
        pairs = list(self.db.find_by_leader(leader=pair.leader()))
        for p in pairs:
            new_p = p.extended_with_internal_frame(frame)
            self.db.add(new_p)
            self._add_label(new_p.leader())
            self._add_label(new_p.follower())
            self._add_ancestor(new_p.leader(), p.leader())
            yield new_p

    def update_globals_after_external_step(self, pair: Pair, frame: Frame) -> Iterable[Pair]:
        new_pair = pair.extended_with_external_frame(frame)
        new_pairs = [new_pair]
        for p in self.db.find_by_leader(leader=pair.follower()):
            if p.dir() != pair.rev_dir() or not self.is_continuity_pair(p):
                new_leader = p.leader().extended_with(frame)
                new_p = p.updated_with_leader(new_leader)
                new_pairs.append(new_p)

        for new_p in new_pairs:
            self.db.add(new_p)
            self._add_label(new_p.leader())
            self._add_label(new_p.follower())

        return new_pairs

    def _step(self, pair: Pair) -> tuple[FrameBuilder, FrameBuilder | None, StepKind] | None:
        return Stepper(self.function, self.k, self.m, self.n).step(pair)

    def psi_internal(self, frameb: FrameBuilder) -> Frame:
        for ptr in self.pointers:
            frameb.upd[ptr.name] = False
        return frameb.build()

    def psi_external(self, pair: Pair, frameb: FrameBuilder) -> Frame:
        sigma = pair.leader()
        tau = pair.follower()
        if tau.origin is None or tau.origin.origin is None:  # index <= 1:
            for p in self.pointers:
                frameb.upd[p.name] = False
        else:
            a_ = next(f.index for f in sigma.slice(1) if f.prev[0] == pair.dir())
            for p in self.pointers:
                frameb.upd[p.name] = not frameb.isnil[p.name] and (
                    any(Here(p.name) in f.events for f in sigma.slice(a_))
                    or any(f.upd[p.name] for f in sigma.slice(a_ + 1))
                )

        return frameb.build()

    def index_after_internal_step(self, old_pair: Pair) -> int:
        if old_pair.leader().frame.prev[0] == Internal():
            return len(old_pair.leader().origin)
        else:
            return len(old_pair.leader())

    def step(self, pair: Pair) -> tuple[Frame, Frame | None, StepKind] | None:
        if pair not in self._step_cache:
            if any(isinstance(event, (OOM, ERR, LOF, Exit)) for event in pair.leader().frame.events):
                self._step_cache[pair] = None
                return None

            step_result = self._step(pair)
            if step_result is None:
                return None
            tau_b_builder, tau_b_false_builder, step_kind = step_result
            if step_kind == StepKind.INTERNAL:
                tau_b_builder.index = self.index_after_internal_step(pair)
                frame = self.psi_internal(tau_b_builder)
                if tau_b_false_builder is None:
                    self._step_cache[pair] = (frame, None, step_kind)
                else:
                    tau_b_false_builder.index = self.index_after_internal_step(pair)
                    frame_false = self.psi_internal(tau_b_false_builder)
                    self._step_cache[pair] = (frame, frame_false, step_kind)
            else:
                tau_b_builder.index = len(pair.follower())
                tau_b = self.psi_external(pair, tau_b_builder)
                self._step_cache[pair] = (tau_b, None, step_kind)
        return self._step_cache[pair]

    def is_continuity_pair(self, pair: Pair) -> bool:
        return self.step(pair) is not None

    def add_internal_step_dependency(self, label: Label):
        for ancestor in self.labels_db.find_ancestors(label):
            pc = label.frame.pc
            instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
            self.dependency_graph.node(label.name, label=f"{label.name}\n{instr}")
            self.dependency_graph.edge(ancestor.name, label.name, label="I", color="red")

    def add_external_step_dependency(self, pair: Pair):
        sigma = pair.follower()
        tau = pair.leader()
        if sigma == tau:
            logger.debug(f"adding self dependency for label {sigma.id}")
        if self.create_dependency_graph:
            self.dependency_graph.node(tau.name, label=f"{tau.name}\n{self.function.instructions[tau.frame.pc]}")
            external_step_label = f"{f'D({pair.child_key})' if pair.dir() == Up() else 'U'}"
            self.dependency_graph.edge(sigma.name, tau.name, label=external_step_label, color="red")
            for ancestor in self.labels_db.find_ancestors(tau):
                self.dependency_graph.edge(ancestor.name, tau.name, label="I")
            if tau.frame.prev is not None and tau.frame.prev[0] != Internal():
                self.dependency_graph.edge(tau.origin.name, tau.name, label="I")

    # def _label_to_json(self, label: Label) -> str:
    #     frames = []
    #     for f in label.iter():
    #         prev = None
    #         if f.prev_dir is not None:
    #             dir, idx = f.prev
    #             prev = {"dir": str(dir), "index": idx}
    #         frames.append(
    #             {
    #                 "index": f.index,
    #                 "active": f.active,
    #                 "pc": f.pc,
    #                 "upd": dict(f.upd),
    #                 "isnil": dict(f.isnil),
    #                 "event": str(f.event),
    #                 "active_child": dict(f.active_child),
    #                 "enum_values": dict(f.enum_values),
    #                 "enum_fields": dict(f.enum_fields),
    #                 "prev": prev,
    #             }
    #         )
    #     payload = {
    #         "id": label.id,
    #         "origin_id": label.origin.id if label.origin is not None else None,
    #         "frames": frames,
    #     }
    #     return json.dumps(payload, separators=(",", ":"), sort_keys=False)

    def _add_label(self, label: Label) -> None:
        self.labels_db.add(label)
        # logger.debug(f"LABEL_JSON {self._label_to_json(label)}")

    def _add_ancestor(self, label: Label, ancestor: Label) -> None:
        self.labels_db.add_ancestor(label, ancestor)
        # logger.debug(f"ANCESTOR {label.id} -> {ancestor.id}")

    def _is_continuity_pair(self, pair: Pair) -> bool:
        if pair in self._step_cache:
            return self._step_cache[pair] is not None
        if pair.leader().frame.events.intersection({Exit(), OOM(), ERR(), LOF()}):
            return False
        step_result = self.step(pair)
        return step_result is not None

    def build_dep_graph(self):
        if self.dependency_graph is None:
            return

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
            if leader.frame.prev is not None and leader.frame.prev[0] == Internal():
                self.add_internal_step_dependency(leader)
            elif leader.frame.prev is not None:
                self.add_external_step_dependency(pair)

    def generate(self):
        # smt2file = SMT2FileBuilder(
        #     {v for v in self.function.vars if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},
        #     {v for v in self.root.sort.pointee.fields.values() if not (sort_of(v).is_ptr() or sort_of(v).is_enum())},  # type: ignore
        # )
        processed: set[Pair] = set()
        queue: deque[Pair] = deque()

        # yielding assertion of first and start frames
        for f in self.start_frames():
            lab = Label.make(*f)
            # smt2file.assert_fact(lab)
            if self.create_dependency_graph:
                self.dependency_graph.node(
                    lab.name, label=f"{lab.name}\n{self.function.instructions[0]}", tooltip="start frame"
                )
        for f in self.first_frames():
            lab = Label.make(f)
            # smt2file.assert_fact(lab)
            if self.create_dependency_graph:
                self.dependency_graph.node(f"{lab.name}", tooltip="first frame")

        for pair in self.start_pairs():
            self.db.add(pair)
            self._add_label(pair.leader())
            self._add_label(pair.follower())
            queue.append(pair)

        for pair in self.first_pairs():
            self.db.add(pair)
            self._add_label(pair.leader())
            self._add_label(pair.follower())

        try:
            while queue:
                pair = queue.popleft()
                if pair in processed:
                    continue
                processed.add(pair)
                step_result = self.step(pair)
                if step_result is None:  # non continuos pair
                    # questo branch copre quei casi in cui il prossimo frame del lace va attaccato a una label esterna alla coppia
                    # in questi casi può succedere che la nuova label esterna sia già stata generata processando un altra coppia
                    # quindi la coppia corrente non verrà aggiornata, perché l'aggiornamento global delle coppie è gia avvenuto
                    new_pairs = tuple(
                        pair.updated_with_leader(leader) for leader in self.labels_db.find_by_origin(pair.leader())
                    )
                    for new_pair in new_pairs:
                        self.db.add(new_pair)
                        self._add_label(new_pair.leader())
                        self._add_label(new_pair.follower())
                        if self._is_continuity_pair(new_pair):
                            queue.append(new_pair)
                    continue
                tau_b, tau_b_false, step_kind = step_result
                # assert tau_b_false is None
                if step_kind == StepKind.INTERNAL:
                    for p in self.db.find_by_leader(pair.leader()):
                        processed.add(p)

                    old_leader = pair.leader()
                    updated_pairs = tuple(self.update_globals_after_internal_step(pair, tau_b))
                    queue.extend(p for p in updated_pairs if self._is_continuity_pair(p))

                    if tau_b_false is None:
                        continue

                    old_leader_false = pair.leader()
                    new_leader_false = old_leader.extended_with(tau_b_false)
                    # self.add_internal_step_dependency(old_leader_false, new_leader_false)

                    if Exit() not in tau_b_false.events:
                        inst = self.function.instructions[pair.leader().frame.pc]
                        match inst:
                            case IfGoto(cond, target, label=label):
                                inst = IfGoto(Not(cond), target, label=label)
                            case FieldAssignExpr(field, expr, label=label) if sort_of(field) == BOOL:
                                inst = FieldAssignExpr(field, Not(expr), label=label)
                            case VarAssignExpr(var, expr, label=label) if sort_of(var) == BOOL:
                                inst = VarAssignExpr(var, Not(expr), label=label)
                            case _:
                                pass
                    updated_pairs_false = tuple(self.update_globals_after_internal_step(pair, tau_b_false))
                    queue.extend(
                        p for p in updated_pairs_false if self._is_continuity_pair(p)
                    )  # queue.append(pair.extended_with_internal_frame(tau_b_false))
                    # smt2file.assert_internal_step(new_leader_false, inst)
                else:
                    new_pair = pair.extended_with_external_frame(tau_b)
                    # self.add_external_step_dependency(new_pair)
                    # update pairs db
                    updated_pairs = (
                        *self.update_globals_after_external_step(pair, tau_b),
                        # se la label leader è stata gia estesa, include nelle nuove coppie tutte quelle coppie che si ottengono
                        # estendendo la leader gia estesa con tau_b, in modo da non perdere nessuna coppia che potrebbe essere di continuita
                        *(
                            new_pair.updated_with_leader(leader)
                            for leader in self.labels_db.find_by_origin(new_pair.leader())
                        ),
                    )
                    queue.extend(pair for pair in updated_pairs if self._is_continuity_pair(pair))

                    # assert external step for tau_b
                    # smt2file.assert_external_step(new_pair)

            logger.info("All pair have been generated")
            # return smt2file
            #
            #
        except Exception as e:
            logger.exception(f"Exception during generation: {e}")

        finally:
            self.build_dep_graph()

            pppsss = sorted((p.parent.id, p.child.id) for p in self.db.pairs_db)
            for p in pppsss:
                logger.info(f"PAIR {p}")

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
