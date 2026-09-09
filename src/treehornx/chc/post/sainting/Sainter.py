
from collections import deque
from dataclasses import dataclass, field, replace
from functools import cache, cached_property
from itertools import chain, product
from typing import Any, Iterable, override

from frozendict import frozendict
from loguru import logger

from treehornx.chc.post.helpers import last_assignment_to_field, child_is_dflt, ptr_here
from treehornx.chc.post.sainting.helpers import missing_child
from treehornx.chc.post.tainting.Tainter import child_is_ptr
from treehornx.chc.utils.helpers import end_of_lace
from treehornx.chc.utils.terminals_discovery import Pair
from treehornx.enum_labels.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_labels.core.Event import FieldAssignP, FieldHere
from treehornx.enum_labels.core.Label import Label
from .SaintDB import SaintDB
from treehornx.chc.post.sainting.core import Q, AutomataTransition, DownStatePropagation, EmptyAcceptance, Initialization, InternalStatePropagation, NonEmptyAcceptance, SaintedLabel, SaintingStep, StartStatePropagation, StructuralChildUpload, UpStatePropagation
from treehornx.chc.post.tainting.core import BoolPlus, TaintedLabel, TaintedPair
from treehornx.enum_labels import KnittedTrees

def consume(iterable: Iterable[Any]):
    for _ in iterable:
        pass

def child_is_struct(label: Label, j: str) -> bool:
    return child_is_dflt(label, j) and label[0].active_child[j]

def child_is_nil(label: Label, j: str) -> bool:
    for frame in reversed(label):
        ass_event = next((e for e in frame.events if isinstance(e, (FieldAssignP, FieldHere)) and e.pfield == j), None)
        if ass_event is None:
            continue
        if isinstance(ass_event, FieldHere):
            return False
        return ass_event.p is None

    return child_is_dflt(label, j) and not label[0].active_child[j]


@dataclass
class Sainter:
    trees: KnittedTrees
    tainted_labels: set[TaintedLabel]
    tainted_pairs: set[TaintedPair]
    db: SaintDB = field(default_factory=SaintDB, init=False)

    @override
    def __hash__(self):
        return 0

    @cached_property
    def field_keys(self) -> tuple[str, ...]:
        field_keys = tuple(key for key in self.trees.child_keys if isinstance(key, str))
        return field_keys

    # the direction is the opposite of the direction of the propagation, i.e. if we are propagating from source to target, then dir is the direction from target to source
    def next_propagable_state(self, source: SaintedLabel, target: SaintedLabel, dir: Dir) -> tuple[int, int, str] | None:
        for ptr_name in source.label.frame.isnil.keys():
            for i1 in range(1, len(source.label)):
                if source.state_ptr[(ptr_name, i1)] != Q():
                    logger.debug(f"next_propagable_state: skipping ({self.label_name(source)}, {self.label_name(target)}, {dir}) because source.state_ptr[({ptr_name}, {i1})] != Q()")
                    continue

                field_keys = list(field_key for field_key in source.label.frame.active_child.keys() if isinstance(field_key, str))

                if any(
                    child_is_ptr(source.label, j, ptr_name, i1)
                    for j in field_keys
                ):
                    child_key = next((j for j in field_keys if child_is_ptr(source.label, j, ptr_name, i1)))
                    logger.debug(f"next_propagable_state: skipping ({self.label_name(source)}, {self.label_name(target)}, {dir}) because child {child_key} is not a pointer to {ptr_name} at index {i1}")
                    continue

                next_frame = next((frame for frame in target.label[1:] if frame.prev == (dir, i1)), None)
                if next_frame is None:
                    logger.debug(f"next_propagable_state: skipping ({self.label_name(source)}, {self.label_name(target)}, {dir}) because target.label has no frame with prev == ({dir}, {i1})")
                    continue
                i2 = next_frame.index

                if not self.lace_succ_s(source, i1, target, i2, target_is_parent=(dir == Up()), E=ptr_name):
                    logger.debug(f"next_propagable_state: skipping ({self.label_name(source)}, {self.label_name(target)}, {dir}) because lace_succ_s returned False for (source, {i1}, target, {i2}, target_is_parent={(dir == Up())}, E={ptr_name})")
                    continue

                logger.debug(f"next_propagable_state: returning (i1={i1}, i2={i2}, p={ptr_name})")
                return (i1, i2, ptr_name)

        return None

    def consistent_state(self, sainted_sigma1: SaintedLabel, i1: int, sainted_sigma2: SaintedLabel, i2: int, E: str | None = None) -> bool:
        for p in set(sainted_sigma1.label.frame.isnil.keys()) - {E}:
            for child_key in self.field_keys:
                if (
                    not child_is_ptr(sainted_sigma1.label, child_key, p, i1) and
                    sainted_sigma1.state_ptr[(p, i1)] == Q() and
                    sainted_sigma2.state_ptr[(p, i2)] != Q()
                ):
                    return False

        return True

    def consistent_child_s(self, sainted_child: SaintedLabel, j: str|int, sainted_parent: SaintedLabel) -> bool:
        if (
            isinstance(j, str) and
            sainted_parent.state_struct_children.get(j, BoolPlus.Bottom) == Q() and
            sainted_child.state_node != Q()
        ):
            return False

        # checking for steps up
        for frame in iter(sainted_parent.label):
            assert frame.prev is not None
            if frame.prev[0] == Down(j):
                a = frame.index
                b = frame.prev[1]
                if not self.consistent_state(sainted_child, a, sainted_parent, b):
                    return False


        # checking for steps down
        for frame in iter(sainted_child.label):
            assert frame.prev is not None
            if frame.prev[0] == Up():
                a = frame.index
                b = frame.prev[1]
                if not self.consistent_state(sainted_parent, a, sainted_child, b):
                    return False

        return True

    def consistent_child_s_exc(self, sainted_child: SaintedLabel, j: str|int, sainted_parent: SaintedLabel, i: int, exc: str|None = None) -> bool:
        if (
            isinstance(j, str) and
            sainted_parent.state_struct_children.get(j, BoolPlus.Bottom) == Q() and
            sainted_child.state_node != Q()
        ):
            return False

        # checking for steps up
        for frame in iter(sainted_parent.label):
            assert frame.prev is not None
            if frame.prev[0] == Down(j):
                a = frame.index
                b = frame.prev[1]
                if a == i and not self.consistent_state(sainted_child, i, sainted_parent, b, exc):
                    return False
                elif a != i and not self.consistent_state(sainted_child, a, sainted_parent, b):
                    return False

        # checking for steps down
        for frame in iter(sainted_child.label):
            assert frame.prev is not None
            if frame.prev[0] == Up():
                a = frame.index
                b = frame.prev[1]
                if a == i and not self.consistent_state(sainted_parent, i, sainted_child, b, exc):
                    return False
                elif a != i and not self.consistent_state(sainted_parent, a, sainted_child, b):
                    return False

        return True



    def lace_succ_s(self, source: SaintedLabel, i1: int, target: SaintedLabel, i2: int, target_is_parent: bool, E: str|None = None) -> bool:
        return True



    def _saint_initalization(self, tainted_label: TaintedLabel) -> Initialization:
        state_node = tainted_label.taint_node
        state_struct_children: frozendict[str, BoolPlus | Q] = frozendict({child_key: BoolPlus.Bottom for child_key in self.field_keys})
        state_ptr: frozendict[tuple[str, int], BoolPlus | Q] = frozendict(tainted_label.taint_ptr)
        sainted_label = SaintedLabel(
            label=tainted_label.label,
            state_node=state_node,
            state_struct_children=state_struct_children,
            state_ptr=state_ptr,
        )
        step = Initialization(
            tainted_label=tainted_label,
            sainted_label=sainted_label,
        )
        return step

    def _start_state_propagation(self, sainted_label: SaintedLabel) -> StartStatePropagation | None:
        if sainted_label.state_node != Q():
            return None
        propagation_coordinates: tuple[str, int]|None = None
        for (p, i), value in sainted_label.state_ptr.items():
            if value != BoolPlus.Top:
                continue
            if not ptr_here(sainted_label.label, i, p):
                continue
            propagation_coordinates = (p, i)
            break
        if propagation_coordinates is None:
            return None
        if sainted_label.state_ptr[propagation_coordinates] == Q():
            return None
        state_ptr_ = sainted_label.state_ptr | {propagation_coordinates: Q()}
        new_sainted_label = SaintedLabel(
            label=sainted_label.label,
            state_node=sainted_label.state_node,
            state_struct_children=sainted_label.state_struct_children,
            state_ptr=state_ptr_
        )
        step = StartStatePropagation(
            sainted_label=sainted_label,
            new_sainted_label=new_sainted_label,
            propagation_coordinates=propagation_coordinates
        )
        return step

    def _state_propagation_by_dir(self, sainted_sigma1: SaintedLabel, sainted_sigma2: SaintedLabel, rev_dir: Dir) -> tuple[SaintedLabel, tuple[str, int, int]] | None:

        next_propagation = self.next_propagable_state(sainted_sigma1, sainted_sigma2, rev_dir)
        if next_propagation is None:
            logger.debug(f"No propagable state found for {self.label_name(sainted_sigma1)}: {sorted(sainted_sigma1.state_ptr.items())}")
            return None
        i1, i2, p = next_propagation

        state_ptr2_ = sainted_sigma2.state_ptr | {(p, i2): Q()}
        new_sainted_sigma2 = replace(sainted_sigma2, state_ptr=state_ptr2_)
        return new_sainted_sigma2, (p, i1, i2)

    def _internal_states_propagation(self, sainted_sigma2: SaintedLabel) -> InternalStatePropagation|None:
        sainted_sigma1 = sainted_sigma2
        propagation_result = self._state_propagation_by_dir(sainted_sigma1, sainted_sigma2, Internal())
        if propagation_result is None:
            return None
        new_sainted_sigma2, propagations = propagation_result
        return InternalStatePropagation(
            sainted_sigma=sainted_sigma2,
            new_sainted_sigma=new_sainted_sigma2,
            prpagations=propagations
        )

    def _child_to_parent_state_propagation(self, sainted_pair: Pair[SaintedLabel]) -> UpStatePropagation|None:
        sainted_sigma1 = sainted_pair.child
        sainted_sigma2 = sainted_pair.parent
        propagation_result = self._state_propagation_by_dir(sainted_sigma1, sainted_sigma2, Down(sainted_pair.child_key))
        if propagation_result is None:
            return None
        new_sainted_sigma2, propagations = propagation_result
        return UpStatePropagation(
            child=sainted_sigma1,
            parent=sainted_sigma2,
            new_parent=new_sainted_sigma2,
            child_key=sainted_pair.child_key,
            prpagations=propagations
        )

    def _parent_to_jth_child_state_propagation(self, sainted_pair: Pair[SaintedLabel]) -> DownStatePropagation|None:
        # logger.debug("sainting parent to child propagation")
        # logger.debug(f"parent: {self.label_name(sainted_pair.parent)}")
        # logger.debug(f"child: {self.label_name(sainted_pair.child)}")
        sainted_sigma1 = sainted_pair.parent
        sainted_sigma2 = sainted_pair.child
        child_key = sainted_pair.child_key
        propagation_result = self._state_propagation_by_dir(sainted_sigma1, sainted_sigma2, Up())
        if propagation_result is None:
            # logger.debug("propagation failed")
            return None
        new_sainted_sigma2, propagations = propagation_result
        # logger.debug(f"new child: {self.label_name(new_sainted_sigma2)}")
        return DownStatePropagation(
            parent=sainted_sigma1,
            child=sainted_sigma2,
            new_child=new_sainted_sigma2,
            child_key=child_key,
            prpagations=propagations
        )

    def _non_structural_child_ready_for_transition(self, sainted_label: SaintedLabel, field_key: str) -> tuple[str, int]|None:
        ptrs = sainted_label.label.frame.isnil.keys()
        indices = range(len(sainted_label.label))
        for p, i in product(ptrs, indices):
            if last_assignment_to_field(sainted_label.label, field_key, p, i) and sainted_label.state_ptr[(p, i)] == Q():
                return (p, i)
        return None

    def _automaton_transition(self, sainted_parent: SaintedLabel) -> AutomataTransition | None:
        # logger.debug(f"evaluatin automaton transition for ({self.label_name(sainted_parent)}, {list((key, self.label_name(child)) for key, child in sainted_children)})")
        if sainted_parent.state_node not in {BoolPlus.Top, BoolPlus.TopPlus}:
            return None
        # Do not consider aux children in the knitted trees since it only refers to node pointed by pointer fields in the node signature
        states_source: dict[str, None|tuple[str, int]|str] = dict()
        ready_for_transition = True
        for child_key in self.field_keys:

            # logger.debug(f"evaluating child {child_key}")

            if child_is_nil(sainted_parent.label, child_key):
                # logger.debug("missing child")
                states_source[child_key] = None

            elif child_is_struct(sainted_parent.label, child_key) and sainted_parent.state_struct_children[child_key] == Q():
                # logger.debug("sainting structural child")
                states_source[child_key] = child_key

            elif (coordinates := self._non_structural_child_ready_for_transition(sainted_parent, child_key)):
                # logger.debug("sainting non structural child")
                states_source[child_key] = coordinates

            else:
                # logger.debug("not ready for transition")
                ready_for_transition = False
                break

        if not ready_for_transition:
            return None

        step = AutomataTransition(
            parent=sainted_parent,
            new_parent=replace(sainted_parent, state_node=Q()),
            states_source=frozendict(states_source)
        )

        return step

    def _structural_child_state_upload(self, sainted_parent: SaintedLabel, sainted_child: SaintedLabel, child_key: str) -> StructuralChildUpload|None:
        if sainted_child.state_node != Q():
            return None

        if not child_is_struct(sainted_parent.label, child_key):
            return None

        new_state_struct_children = sainted_parent.state_struct_children | frozendict({child_key: Q()})
        new_sainted_parent = replace(sainted_parent, state_struct_children=new_state_struct_children)
        step = StructuralChildUpload(
            parent=sainted_parent,
            child=sainted_child,
            new_parent=new_sainted_parent,
            child_key=child_key
        )
        return step

    def _non_empty_acceptance(self, sainted_label: SaintedLabel) -> NonEmptyAcceptance|None:
        if sainted_label.state_node != Q():
            return None

        p_at = self.trees.root_name
        if not any(
            ptr_here(sainted_label.label, i, p_at) and sainted_label.state_ptr[p_at, i] == BoolPlus.TopPlus
            for i in range(1, len(sainted_label.label))):
            logger.debug(f"non empty acceptance failed for {self.label_name(sainted_label)}: no topplus at root")
            return None

        return NonEmptyAcceptance(sainted_label=sainted_label)

    def _empty_acceptance(self, sainted_label: SaintedLabel) -> EmptyAcceptance|None:
        if not end_of_lace(sainted_label.label):
            return None

        p_at = self.trees.root_name
        if not sainted_label.label.frame.isnil[p_at]:
            return None

        return EmptyAcceptance(sainted_label=sainted_label)

    @cache
    def label_name(self, sainted_label: SaintedLabel|None) -> str:
        if sainted_label is None:
            return "None"
        lab_id = self.trees.id(sainted_label.label)
        state_ptr = sainted_label.state_ptr
        state_ptr_id = 0
        for (p, i) in sorted(state_ptr.keys()):
           match state_ptr[(p, i)]:
               case BoolPlus() as value:
                   state_ptr_id = (state_ptr_id << 2) + value.value
               case Q():
                   state_ptr_id = (state_ptr_id << 2) + 3
        state_node = sainted_label.state_node
        match state_node:
            case BoolPlus():
                state_node_id = state_node.value
            case Q():
                state_node_id = 3
        state_struct_children_id = 0
        for child_key in sorted(sainted_label.state_struct_children.keys()):
            match sainted_label.state_struct_children[child_key]:
                case BoolPlus() as value:
                    state_struct_children_id = (state_struct_children_id << 2) + value.value
                case Q():
                    state_struct_children_id = (state_struct_children_id << 2) + 3
        name = f"{lab_id}_{state_node_id}_{state_ptr_id}_{state_struct_children_id}"
        # logger.debug(f"saint_ptr_map({name}) = {state_ptr}")
        return name


    def tainted_label_name(self, tainted_label: TaintedLabel) -> str:
        taint_node_id = tainted_label.taint_node.value
        taint_ptr = sorted(tainted_label.taint_ptr.keys())
        taint_ptr_id = 0
        for key in taint_ptr:
            taint_ptr_id = (taint_ptr_id << 2) | tainted_label.taint_ptr[key].value
        name = f"{self.trees.id(tainted_label.label)}_{taint_node_id}_{taint_ptr_id}"
        # print(f"taint_ptr_map({name}): {taint_ptr}")
        return name

    def saint(self) -> tuple[set[SaintingStep], set[SaintedLabel], set[Pair[SaintedLabel]]]:
        sainting_steps: set[SaintingStep] = set()
        label_queue: deque[SaintedLabel] = deque()
        pair_queue: deque[Pair[SaintedLabel]] = deque()
        unallowed_external_propagations: set[SaintedLabel] = set()
        enqueued: set[SaintedLabel|Pair[SaintedLabel]] = set(chain(label_queue, pair_queue))

        def add_pair(pair: Pair[SaintedLabel]):
            if not self.db.contains_pair(pair):
                # logger.debug(f"adding pair: ({self.label_name(pair.parent)}, {self.label_name(pair.child)}, {pair.child_key})")
                self.db.add_pair(pair)

        def enqueue_label(label: SaintedLabel):
            if label not in enqueued:
                logger.debug(f"enqueuing sainted label: {self.label_name(label)}")
                enqueued.add(label)
                label_queue.append(label)

        def enqueue_pair(pair: Pair[SaintedLabel]):
            if pair not in enqueued and pair.parent:
                enqueued.add(pair)
                pair_queue.append(pair)
                logger.debug(f"enqueuing sainted pair: ({self.label_name(pair.parent)}, {self.label_name(pair.child)}, {pair.child_key})")

        for tainted_label in self.tainted_labels:
            step = self._saint_initalization(tainted_label)
            # logger.debug(f"tainted label init: {self.tainted_label_name(tainted_label)} -> {self.label_name(step.sainted_label)}")
            sainting_steps.add(step)
            enqueue_label(step.sainted_label)
            self.db.add_label(step.sainted_label)

        for tainted_pair in self.tainted_pairs:
            sainted_pair = Pair[SaintedLabel](
                parent=self._saint_initalization(tainted_pair.parent).sainted_label,
                child=self._saint_initalization(tainted_pair.child).sainted_label,
                child_key=tainted_pair.child_key
            )
            add_pair(sainted_pair)
            enqueue_pair(sainted_pair)

        def updated_pairs_on_new_child(label: SaintedLabel, new_label: SaintedLabel) -> Iterable[Pair[SaintedLabel]]:
            for pair in self.db.pairs_by_child(label):
                new_pair = replace(pair, child=new_label)
                yield new_pair

        def updated_pairs_on_new_label(label: SaintedLabel, new_label: SaintedLabel, exclude_dir: set[Dir] = set()) -> Iterable[Pair[SaintedLabel]]:
            if Up() not in exclude_dir:
                yield from updated_pairs_on_new_child(label, new_label)

            for child_key in self.trees.child_keys:
                if Down(child_key) not in exclude_dir:
                    for pair in self.db.pairs_by_parent_and_child_key(label, child_key):
                        new_pair = replace(pair, parent=new_label)
                        yield new_pair

        def update_pairs_on_new_label(label: SaintedLabel, new_label: SaintedLabel, exclude_dir: set[Dir] = set()):
            for new_pair in updated_pairs_on_new_label(label, new_label, exclude_dir):
                add_pair(new_pair)

        def is_knitted_tree_leaf(label: SaintedLabel) -> bool:
            label_children = list(chain.from_iterable(
                self.db.pairs_by_parent_and_child_key(label, child_key)
                for child_key in self.trees.child_keys
            ))
            is_leaf = not bool(label_children)
            # logger.debug(f"{self.label_name(label)} is {"" if is_leaf else "not "}leaf")
            return is_leaf

        while label_queue:

            while label_queue:

                old_sainted_label = label_queue.popleft()

                logger.debug(f"sainting extracting label: {self.label_name(old_sainted_label)}")
                new_sainted_label = old_sainted_label
                step = self._start_state_propagation(new_sainted_label)
                if step is not None:
                    # logger.debug(f"sainting start state propagation: {self.label_name(step.sainted_label)} -> {self.label_name(step.new_sainted_label)}")
                    sainting_steps.add(step)
                    unallowed_external_propagations.add(new_sainted_label)
                    new_sainted_label = step.new_sainted_label
                    self.db.add_label(new_sainted_label)


                step = self._internal_states_propagation(new_sainted_label)
                if step is not None:
                    # logger.debug(f"sainting internal state propagation: {self.label_name(step.sainted_sigma)} -> {self.label_name(step.new_sainted_sigma)}")
                    sainting_steps.add(step)
                    unallowed_external_propagations.add(new_sainted_label)
                    new_sainted_label = step.new_sainted_sigma
                    self.db.add_label(new_sainted_label)

                step = self._automaton_transition(new_sainted_label)
                if step is not None:
                    logger.debug(f"sainting automaton transition: {self.label_name(step.parent)} -> {self.label_name(step.new_parent)}")
                    sainting_steps.add(step)
                    unallowed_external_propagations.add(new_sainted_label)
                    new_sainted_label = step.new_parent
                    self.db.add_label(new_sainted_label)

                enqueue_label(new_sainted_label)
                for new_pair in updated_pairs_on_new_label(old_sainted_label, new_sainted_label):
                    add_pair(new_pair)
                    enqueue_pair(new_pair)

            while pair_queue:
                pair = pair_queue.popleft()
                logger.debug(f"sainting extracting pair: ({self.label_name(pair.parent)}, {self.label_name(pair.child)}, {pair.child_key})")
                step = self._child_to_parent_state_propagation(pair)
                if step is not None:
                    logger.debug("sainting child to parent propagation")
                    logger.debug(f"parent: {self.label_name(step.parent)}")
                    logger.debug(f"child: {self.label_name(step.child)}")
                    logger.debug(f"new parent: {self.label_name(step.new_parent)}")
                    sainting_steps.add(step)
                    new_pair = replace(pair, parent=step.new_parent)
                    add_pair(new_pair)
                    enqueue_label(step.new_parent)
                    update_pairs_on_new_label(step.parent, step.new_parent, exclude_dir={Down(pair.child_key)})


                step = self._parent_to_jth_child_state_propagation(pair)
                if step is not None:
                    logger.debug("sainting parent to child propagation")
                    logger.debug(f"parent: {self.label_name(step.parent)}")
                    logger.debug(f"child: {self.label_name(step.child)}")
                    logger.debug(f"new child: {self.label_name(step.new_child)}")
                    sainting_steps.add(step)
                    new_pair = replace(pair, child=step.new_child)
                    add_pair(new_pair)
                    enqueue_label(step.new_child)
                    update_pairs_on_new_label(step.child, step.new_child, exclude_dir={Up()})

                if isinstance(pair.child_key, int):
                   continue
                step = self._structural_child_state_upload(pair.parent, pair.child, pair.child_key)
                if step is not None:
                    logger.debug(f"sainting structural child state upload: (parent = {self.label_name(step.parent)}, child = {self.label_name(step.child)}) -> {self.label_name(step.new_parent)}")
                    logger.debug(f"parent: {self.label_name(step.parent)}")
                    logger.debug(f"child: {self.label_name(step.child)}")
                    logger.debug(f"new parent: {self.label_name(step.new_parent)}")
                    sainting_steps.add(step)
                    new_pair = replace(pair, parent=step.new_parent)
                    add_pair(new_pair)
                    enqueue_label(step.new_parent)
                    update_pairs_on_new_label(step.parent, step.new_parent, exclude_dir={Down(pair.child_key)})

        for label in self.db.labels():
            step = self._empty_acceptance(label)
            if step is not None:
                logger.debug(f"sainting empty acceptance: {self.label_name(step.sainted_label)}")
                sainting_steps.add(step)
            step = self._non_empty_acceptance(label)
            if step is not None:
                logger.debug(f"sainting non empty acceptance: {self.label_name(step.sainted_label)}")
                sainting_steps.add(step)

        return sainting_steps, set(self.db.labels()), set(self.db.pairs())
