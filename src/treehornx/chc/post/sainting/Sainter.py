
from collections import deque
from dataclasses import dataclass, field, replace
from functools import cache, cached_property
from itertools import chain, product
from typing import Any, Iterable, override

from frozendict import frozendict
from loguru import logger

from treehornx.chc.post.helpers import last_assignment_to_field, no_assignment_to_field, ptr_here
from treehornx.chc.post.sainting.helpers import missing_child
from treehornx.chc.utils.terminals_discovery import Pair
from treehornx.enum_labels.core.Dir import Dir, Down, Internal, Up
from .SaintDB import SaintDB
from treehornx.chc.post.sainting.core import Q, Acceptance, AutomataTransition, DownStatePropagation, Initialization, InternalStatePropagation, SaintedLabel, SaintingStep, StartStatePropagation, UpStatePropagation
from treehornx.chc.post.tainting.core import TaintedLabel, TaintedPair
from treehornx.enum_labels import KnittedTrees

def consume(iterable: Iterable[Any]):
    for _ in iterable:
        pass

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

    def _saint_initalization(self, tainted_label: TaintedLabel) -> Initialization:
        state_node = tainted_label.taint_node
        state_ptr: frozendict[tuple[str, int], bool | Q] = frozendict(tainted_label.taint_ptr)
        sainted_label = SaintedLabel(
            label=tainted_label.label,
            state_node=state_node,
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
        state_ptr_update: dict[tuple[str, int], bool | Q] = {}
        for (p, i), value in sainted_label.state_ptr.items():
            if not isinstance(value, bool) or not value:
                continue
            if not ptr_here(sainted_label.label, i, p):
                continue
            state_ptr_update[(p, i)] = Q()
        if not state_ptr_update:
            return None
        if all(state_ptr_update[key] == sainted_label.state_ptr[key] for key in state_ptr_update):
            return None
        state_ptr_ = sainted_label.state_ptr | frozendict(state_ptr_update)
        new_sainted_label = SaintedLabel(
            label=sainted_label.label,
            state_node=sainted_label.state_node,
            state_ptr=state_ptr_
        )
        step = StartStatePropagation(
            sainted_label=sainted_label,
            new_sainted_label=new_sainted_label,
            propagation_coordinates=tuple(state_ptr_update.keys())
        )
        return step

    def _state_propagation_by_dir(self, sainted_sigma1: SaintedLabel, sainted_sigma2: SaintedLabel, rev_dir: Dir) -> tuple[SaintedLabel, tuple[tuple[str, int, int], ...]] | None:

        sigma2 = sainted_sigma2.label # follows
        sigma1 = sainted_sigma1.label # previous
        state_ptr2 = sainted_sigma2.state_ptr
        state_ptr1 = sainted_sigma1.state_ptr
        state_ptr2_update: dict[tuple[str, int], bool|Q] = dict()
        coordinates_update: list[tuple[str, int, int]] = []
        for (p, i2) in state_ptr2:
            sigma2_i2 = sigma2[i2]
            assert sigma2_i2.prev is not None
            if sigma2_i2.prev[0] != rev_dir:
                continue
            i1 = sigma2_i2.prev[1]
            # print(f"sigma2_i2.prev: {sigma2_i2.prev}")
            if state_ptr1[(p, i1)] != Q():
                continue

            if any(last_assignment_to_field(sigma1, field_key, p, i1) for field_key in self.field_keys):
                continue

            state_ptr2_update[(p, i2)] = Q()
            coordinates_update.append((p, i1, i2))

        if not state_ptr2_update:
            return None

        if all(state_ptr2_update[key] == state_ptr2[key] for key in state_ptr2_update):
            return None

        state_ptr2_ = state_ptr2 | state_ptr2_update
        new_sainted_sigma2 = replace(sainted_sigma2, state_ptr=state_ptr2_)
        if self.trees.id(sainted_sigma2.label) == 29:
            assert len(state_ptr2_) == 6
        return new_sainted_sigma2, tuple(coordinates_update)

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
            new_sainted_sigma2=new_sainted_sigma2,
            child_key=sainted_pair.child_key,
            prpagations=propagations
        )

    def _parent_to_jth_child_state_propagation(self, sainted_pair: Pair[SaintedLabel]) -> DownStatePropagation|None:
        logger.debug("sainting parent to child propagation")
        logger.debug(f"parent: {self.label_name(sainted_pair.parent)}")
        logger.debug(f"child: {self.label_name(sainted_pair.child)}")
        sainted_sigma1 = sainted_pair.parent
        sainted_sigma2 = sainted_pair.child
        child_key = sainted_pair.child_key
        propagation_result = self._state_propagation_by_dir(sainted_sigma1, sainted_sigma2, Up())
        if propagation_result is None:
            logger.debug("propagation failed")
            return None
        new_sainted_sigma2, propagations = propagation_result
        logger.debug(f"new child: {self.label_name(new_sainted_sigma2)}")
        return DownStatePropagation(
            parent=sainted_sigma1,
            sainted_sigma2=sainted_sigma2,
            new_sainted_sigma2=new_sainted_sigma2,
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

    def _automaton_transition(self, sainted_parent: SaintedLabel, sainted_children: tuple[tuple[str, SaintedLabel|None], ...]) -> AutomataTransition | None:
        logger.debug(f"evaluatin automaton transition for ({self.label_name(sainted_parent)}, {list((key, self.label_name(child)) for key, child in sainted_children)})")
        if sainted_parent.state_node is not True:
            return None
        # Do not consider aux children in the knitted trees since it only refers to node pointed by pointer fields in the node signature
        children_dict: dict[str, SaintedLabel | None] = dict()
        states_source: dict[str, None|tuple[str, int]|SaintedLabel] = dict()
        ready_for_transition = True
        for child_key, child in sainted_children:

            logger.debug(f"evaluating child {child_key}")

            if child is None or missing_child(sainted_parent.label, child_key):
                logger.debug("missing child")
                children_dict[child_key] = None
                states_source[child_key] = None

            elif no_assignment_to_field(sainted_parent.label, child_key) and child.state_node == Q():
                logger.debug("sainting structural child")
                children_dict[child_key] = child
                states_source[child_key] = child

            elif (coordinates := self._non_structural_child_ready_for_transition(sainted_parent, child_key)):
                logger.debug("sainting non structural child")
                children_dict[child_key] = None
                states_source[child_key] = coordinates

            else:
                logger.debug("not ready for transition")
                ready_for_transition = False
                break

        if not ready_for_transition:
            return None

        step = AutomataTransition(
            parent=sainted_parent,
            children=frozendict(children_dict),
            new_parent=replace(sainted_parent, state_node=Q()),
            states_source=frozendict(states_source)
        )

        return step

    def _acceptance(self, sainted_label: SaintedLabel) -> Acceptance|None:
        if sainted_label.state_node != Q():
            return None

        p_at = self.trees.root_name
        if not any(
            ptr_here(sainted_label.label, i, p_at) and sainted_label.state_ptr[p_at, i] is True
            for i in range(len(sainted_label.label))):
            return None

        return Acceptance(sainted_label=sainted_label)

    @cache
    def label_name(self, sainted_label: SaintedLabel|None) -> str:
        if sainted_label is None:
            return "None"
        lab_id = self.trees.id(sainted_label.label)
        state_ptr = sainted_label.state_ptr
        state_ptr_id = 0
        for (p, i) in sorted(state_ptr.keys()):
           match state_ptr[p, i]:
               case True:
                   state_ptr_id = (state_ptr_id << 2) + 1
               case False:
                   state_ptr_id = (state_ptr_id << 2)
               case Q():
                   state_ptr_id = (state_ptr_id << 2) + 2
        state_node = sainted_label.state_node
        match state_node:
            case True:
                state_node_id = 1
            case False:
                state_node_id = 0
            case Q():
                state_node_id = 2
        name = f"{lab_id}_{state_node_id}_{state_ptr_id}"
        logger.debug(f"saint_ptr_map({name}) = {state_ptr}")
        return name

    def consistent_state(self, sainted_sigma1: SaintedLabel, a: int, sainted_sigma2: SaintedLabel, b: int) -> bool:
        for field_key in self.field_keys:
            if not(
                sainted_sigma2.state_node == Q() and
                ptr_here(sainted_sigma2.label, b, field_key)
            ) and sainted_sigma2.state_ptr[(field_key, b)] == Q() and sainted_sigma1.state_ptr[(field_key, a)] != Q():
                return False

        return True


            #and sainted_sigma1.state_ptr[(field_key, a)] == Q():

    def consistent_child_S(self, sainted_sigma: SaintedLabel, child_key: int | str, sainted_tau: SaintedLabel) -> bool:
        for frame in iter(sainted_sigma.label): # step down
            if frame.prev is None:
               continue

            if frame.prev[0] != Down(child_key):
                continue

            a = frame.index
            b = frame.prev[1]

            if not self.consistent_state(sainted_sigma, a, sainted_tau, b):
                return False

        for frame in iter(sainted_tau.label): # step up
            if frame.prev is None:
                continue

            if frame.prev[0] != Up():
                continue

            a = frame.index
            b = frame.prev[1]

            if not self.consistent_state(sainted_tau, a, sainted_sigma, b):
                return False

        return True


    def tainted_label_name(self, tainted_label: TaintedLabel) -> str:
        taint_node_id = 1 if tainted_label.taint_node else 0
        taint_ptr = sorted(tainted_label.taint_ptr.keys())
        taint_ptr_id = 0
        for key in taint_ptr:
            taint_ptr_id = (taint_ptr_id << 1) | tainted_label.taint_ptr[key]
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
                logger.debug(f"adding pair: ({self.label_name(pair.parent)}, {self.label_name(pair.child)}, {pair.child_key})")
                self.db.add_pair(pair)

        def enqueue_label(label: SaintedLabel):
            if label not in enqueued and label not in unallowed_external_propagations:
                enqueued.add(label)
                label_queue.append(label)

        def enqueue_pair(pair: Pair[SaintedLabel]):
            if pair not in enqueued and pair.parent not in unallowed_external_propagations and pair.child not in unallowed_external_propagations:
                enqueued.add(pair)
                pair_queue.append(pair)
                logger.debug(f"enqueuing satined pair: ({self.label_name(pair.parent)}, {self.label_name(pair.child)}, {pair.child_key})")

        for tainted_label in self.tainted_labels:
            step = self._saint_initalization(tainted_label)
            logger.debug(f"tainted label init: {self.tainted_label_name(tainted_label)} -> {self.label_name(step.sainted_label)}")
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
            logger.debug(f"{self.label_name(label)} is {"" if is_leaf else "not "}leaf")
            return is_leaf

        while label_queue:

            while label_queue:

                old_sainted_label = label_queue.popleft()

                logger.debug(f"sainting extracting label: {self.label_name(old_sainted_label)}")
                new_sainted_label = old_sainted_label
                step = self._start_state_propagation(new_sainted_label)
                if step is not None:
                    logger.debug(f"sainting start state propagation: {self.label_name(step.sainted_label)} -> {self.label_name(step.new_sainted_label)}")
                    sainting_steps.add(step)
                    unallowed_external_propagations.add(new_sainted_label)
                    new_sainted_label = step.new_sainted_label
                    self.db.add_label(new_sainted_label)


                step = self._internal_states_propagation(new_sainted_label)
                if step is not None:
                    logger.debug(f"sainting internal state propagation: {self.label_name(step.sainted_sigma)} -> {self.label_name(step.new_sainted_sigma)}")
                    sainting_steps.add(step)
                    unallowed_external_propagations.add(new_sainted_label)
                    new_sainted_label = step.new_sainted_sigma
                    self.db.add_label(new_sainted_label)


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
                    logger.debug(f"new parent: {self.label_name(step.new_sainted_sigma2)}")
                    sainting_steps.add(step)
                    new_pair = replace(pair, parent=step.new_sainted_sigma2)
                    add_pair(new_pair)
                    enqueue_label(step.new_sainted_sigma2)
                    update_pairs_on_new_label(step.parent, step.new_sainted_sigma2, exclude_dir={Down(pair.child_key)})

                step = self._parent_to_jth_child_state_propagation(pair)
                if step is not None:
                    logger.debug("sainting parent to child propagation")
                    logger.debug(f"parent: {self.label_name(step.parent)}")
                    logger.debug(f"child: {self.label_name(step.sainted_sigma2)}")
                    logger.debug(f"new child: {self.label_name(step.new_sainted_sigma2)}")
                    sainting_steps.add(step)
                    new_pair = replace(pair, child=step.new_sainted_sigma2)
                    add_pair(new_pair)
                    enqueue_label(step.new_sainted_sigma2)
                    update_pairs_on_new_label(step.sainted_sigma2, step.new_sainted_sigma2, exclude_dir={Up()})

            for sainted_label in list(self.db.labels()):
                logger.debug(f"sainting Trying automaton transition on {self.label_name(sainted_label)}")
                if is_knitted_tree_leaf(sainted_label):
                    logger.debug("no possible children for structural transition")
                    possible_children = list(((j, None),) for j in self.field_keys)
                else:
                    possible_children = [
                        tuple(map(lambda pair: (j, pair.child), self.db.pairs_by_parent_and_child_key(sainted_label, j)))
                        for j in self.field_keys
                    ]
                for children in product(*possible_children):
                    logger.debug(f"attempting transition with children: {list((child_key, (self.label_name(child) if child else None)) for child_key, child in children)}")
                    step = self._automaton_transition(sainted_label, children)
                    if step is not None and step not in sainting_steps:
                        logger.debug("sainting Automaton transition")
                        logger.debug(f"parent: {self.label_name(step.parent)}")
                        logger.debug(f"children: {list((child_key, self.label_name(child)) for child_key, child in children)}")
                        logger.debug(f"new parent: {self.label_name(step.new_parent)}")
                        sainting_steps.add(step)
                        self.db.add_label(step.new_parent)
                        enqueue_label(step.new_parent)
                        for child_key, child in children:
                            if child is None:
                                continue
                            new_pair = Pair[SaintedLabel](
                                parent=step.new_parent,
                                child=child,
                                child_key=child_key
                            )
                            add_pair(new_pair)
                        exclude_dir: set[Dir] = {Down(child_key) for child_key in self.field_keys}
                        update_pairs_on_new_label(step.parent, step.new_parent, exclude_dir)
                    else:
                        logger.debug("automaton transition failed")

        for label in self.db.labels():
            step = self._acceptance(label)
            if step is not None:
                logger.debug(f"sainting acceptance: {self.label_name(step.sainted_label)}")
                sainting_steps.add(step)

        return sainting_steps, set(self.db.labels()), set(self.db.pairs())
