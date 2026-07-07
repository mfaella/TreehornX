from collections import defaultdict, deque
from dataclasses import dataclass
from functools import cached_property
from itertools import chain, product
from typing import Iterable, Iterator

from frozendict import frozendict
from loguru import logger

from treehornx.chc.post.helpers import last_assignment_to_field, no_assignment_to_field, ptr_here
from treehornx.chc.post.tainting import TaintDB
from treehornx.chc.post.tainting import (
    DownTaintingPropagation,
    InternalTaintingPropagation,
    LookingForRoot,
    PointerTaintingEnd,
    StartOfPointerTainting,
    StructuralChildTainting,
    TaintedLabel,
    TaintedLabelFactory,
    TaintedPair,
    TaintedPairFactory,
    TaintingInitialization,
    TaintingStep,
    UpTaintingPropagation,
)
from treehornx.chc.utils import generate_terminals
from treehornx.chc.utils.helpers import end_of_lace
from treehornx.chc.utils.terminals_discovery import Pair
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_labels.core.Label import Label


@dataclass
class Tainter:
    root_name: str
    trees: KnittedTrees

    def label_name(self, tainted_label: TaintedLabel) -> str:
        taint_node_id = 1 if tainted_label.taint_node else 0
        taint_ptr = sorted(tainted_label.taint_ptr.keys())
        taint_ptr_id = 0
        for key in taint_ptr:
            taint_ptr_id = (taint_ptr_id << 1) | tainted_label.taint_ptr[key]
        name = f"{self.trees.id(tainted_label.label)}_{taint_node_id}_{taint_ptr_id}"
        # print(f"taint_ptr_map({name}): {taint_ptr}")
        return name

    @cached_property
    def ptr_children(self) -> tuple[str, ...]:
        return tuple(child_key for child_key in self.trees.child_keys if isinstance(child_key, str))

    @cached_property
    def tainted_label_factory(self) -> TaintedLabelFactory:
        return TaintedLabelFactory()

    @cached_property
    def tainted_pair_factory(self) -> TaintedPairFactory:
        return TaintedPairFactory()

    def _lace_prevs_plus(
        self,
        tainted_sigma2: TaintedLabel,
        i2: int,
        P_Tainted: set[TaintedPair],  # noqa: N803
    ) -> Iterator[tuple[TaintedLabel, int]]:
        sigma2 = tainted_sigma2.label
        sigma2_i2 = sigma2.origin_at(i2)
        assert sigma2_i2.frame.prev is not None
        assert sigma2_i2.origin is not None
        i1 = sigma2_i2.frame.prev[1]
        match sigma2_i2.frame.prev[0]:
            case Internal():
                yield tainted_sigma2, i1
            case Up():
                for p in P_Tainted:
                    if p.child == tainted_sigma2:
                        yield p.parent, i1
            case Down(j):
                for p in P_Tainted:
                    if p.parent == tainted_sigma2 and p.child_key == j:
                        yield p.child, i1

    def _init_tainted_label(self, lab: Label) -> TaintedLabel:
        lab_len = len(lab)
        tainted_ptr: frozendict[tuple[str, int], bool] = frozendict(
            {(ptr, i): False for i, ptr in product(range(1, lab_len), lab.frame.isnil.keys())}
        )
        if end_of_lace(lab) and not lab.frame.isnil[self.root_name]:
            tainted_ptr = tainted_ptr.set((self.root_name, lab_len - 1), True)
        return self.tainted_label_factory.create(label=lab, taint_node=False, taint_ptr=tainted_ptr)

    def _structural_child_tainting(self, pair: TaintedPair) -> StructuralChildTainting | None:
        sigma = pair.parent
        tau = pair.child
        child_key = pair.child_key
        if not sigma.taint_node:
            return None
        if tau.taint_node:
            return None
        if isinstance(child_key, int):
            return None
        if not no_assignment_to_field(sigma.label, child_key):
            return None
        if not tau.label.frame.active:
            return None
        new_tau = self.tainted_label_factory.replace(tau, taint_node=True)
        return StructuralChildTainting(parent=sigma, child=tau, new_child=new_tau, child_key=child_key)

    def _start_of_pointer_tainting(self, tlab: TaintedLabel) -> StartOfPointerTainting | None:
        if not tlab.taint_node:
            return None
        taint_ptr_update: dict[tuple[str, int], bool] = dict()
        for child_ptr in self.ptr_children:
            for (p, i) in product(tlab.label.frame.isnil.keys(), range(1, len(tlab.label))):
                if not last_assignment_to_field(tlab.label, child_ptr, p, i):
                    continue
                # The original version in te paper taint the same frame, not the previous one. In this compressed version tainting the same node
                # may lead to an error, due to the new event FieldHere. In the compressed encoding, if a frame contains FieldAssignP(pfield, p) and Here(p)
                # it means that pfield := p was executed before p := here. Instead if the frame contains FieldHere(pfield) and Here(p) it means that p := here was executed before pfield := p.
                # In the first case, if we taint the same frame, the tainter will think we terminated the tainting of p, instead it is just started.

                # We are sure that if an assignment to a field occurs it is generated by an internal step or it is in the first frame of the root.
                # In the first case it is trivially sound, it just propagate the tainting backward because we know that the pointer points somewhere else due to the previous invariant.
                # In the second case because the lace never crossed any node but the root, we are sure that the pointer either points to the root or it is nil.
                # If it points to the root there is an event FieldHere(pfield) which is discarded by last_assignment_to_field, that is to say tainting is not started.
                # If it points to nil there is no need of tainting.
                taint_ptr_update[(p, i-1)] = True
                assert i-1 > 0
        if not taint_ptr_update:
            return None
        taint_ptr_ = tlab.taint_ptr | frozendict(taint_ptr_update)
        if taint_ptr_ == tlab.taint_ptr:
            return None
        new_tlab = self.tainted_label_factory.replace(tlab, taint_ptr=taint_ptr_)
        return StartOfPointerTainting(lab=tlab, new_lab=new_tlab)

    def _end_of_pointer_tainting(self, tlab: TaintedLabel) -> PointerTaintingEnd | None:
        if not tlab.label.frame.active:
            logger.debug(f"Label {self.label_name(tlab)} is not active, skipping end of pointer tainting")
            return None
        for (p, i), taint_flag in tlab.taint_ptr.items():
            if taint_flag and ptr_here(tlab.label, i, p):
                new_tlab = self.tainted_label_factory.replace(tlab, taint_node=True)
                step = PointerTaintingEnd(lab=tlab, new_lab=new_tlab)
                logger.debug(f"Label {self.label_name(tlab)}: pointer {p} at position {i} is tainted, ptr_here is {ptr_here(tlab.label, i, p)}, end of pointer tainting -> {self.label_name(new_tlab)}")
                if tlab == new_tlab:
                    return None
                return step
            else:
                logger.debug(f"Label {self.label_name(tlab)}: pointer {p} at position {i} is {'tainted' if taint_flag else 'not tainted'}, ptr_here is {ptr_here(tlab.label, i, p)}")

        return None

    def _taint_ptr_propagation_update_by_dir(
        self, tainted_sigma2: TaintedLabel, dir: Dir
    ) -> frozendict[tuple[str, int], bool]:
        taint_ptr_update: dict[tuple[str, int], bool] = dict()
        for (p, i2), tainted in tainted_sigma2.taint_ptr.items():
            if not tainted:
                continue
            sigma2_i2 = tainted_sigma2.label.origin_at(i2)
            if ptr_here(sigma2_i2, i2, p):
                continue
            assert sigma2_i2.frame.prev is not None
            assert sigma2_i2.origin is not None
            sigma2_i2_dir = sigma2_i2.frame.prev[0]
            if sigma2_i2_dir != dir:
                continue
            i1 = sigma2_i2.frame.prev[1]
            taint_ptr_update[(p, i1)] = True
        return frozendict(taint_ptr_update)

    def _ptr_taint_propagation_by_dir(self, tainted_sigma1: TaintedLabel, tainted_sigma2: TaintedLabel, dir: Dir) -> TaintedLabel | None:

        sigma2 = tainted_sigma2.label
        sigma1 = tainted_sigma1.label
        taint_ptr2 = tainted_sigma2.taint_ptr
        taint_ptr1 = tainted_sigma1.taint_ptr
        taint_ptr1_update: dict[tuple[str, int], bool] = dict()

        for (p, i2) in taint_ptr2:
            if not taint_ptr2[(p, i2)]:
                continue
            if ptr_here(sigma2, i2, p):
                continue
            sigma2_i2 = sigma2[i2]
            assert sigma2_i2.prev is not None
            if sigma2_i2.prev[0] != dir:
                continue
            i1 = sigma2_i2.prev[1]
            taint_ptr1_update[(p, i1)] = True

        if not taint_ptr1_update:
            return None

        taint_ptr1_ = taint_ptr1 | taint_ptr1_update
        if taint_ptr1_ == taint_ptr1:
            return None
        new_tainted_sigma1 = self.tainted_label_factory.replace(tainted_sigma1, taint_ptr=taint_ptr1_)
        return new_tainted_sigma1

    def _internal_ptr_taint_propagation(self, tainted_sigma2: TaintedLabel) -> InternalTaintingPropagation | None:
        tainted_sigma1 = tainted_sigma2
        new_tainted_sigma1 = self._ptr_taint_propagation_by_dir(tainted_sigma1, tainted_sigma2, Internal())
        if new_tainted_sigma1 is None:
            return None
        return InternalTaintingPropagation(lab=tainted_sigma2, new_lab=new_tainted_sigma1)

    def _parent_to_jth_child_ptr_taint_propagation(self, pair: TaintedPair) -> DownTaintingPropagation | None:
        tainted_sigma2 = pair.parent
        tainted_sigma1 = pair.child
        child_key = pair.child_key
        new_tainted_sigma1 = self._ptr_taint_propagation_by_dir(tainted_sigma2=tainted_sigma2, tainted_sigma1=tainted_sigma1, dir=Down(child_key))
        if new_tainted_sigma1 is None:
            return None
        return DownTaintingPropagation(
            parent=tainted_sigma2, child=tainted_sigma1, child_key=child_key, new_child=new_tainted_sigma1
        )

    def _child_to_parent_ptr_taint_propagation(self, pair: TaintedPair) -> UpTaintingPropagation | None:
        tainted_sigma2 = pair.child
        tainted_sigma1 = pair.parent
        child_key = pair.child_key

        new_tainted_sigma1 = self._ptr_taint_propagation_by_dir(tainted_sigma1=tainted_sigma1, tainted_sigma2=tainted_sigma2, dir=Up())
        if new_tainted_sigma1 is None:
            return None
        return UpTaintingPropagation(
            parent=tainted_sigma1, child=tainted_sigma2, child_key=child_key, new_parent=new_tainted_sigma1
        )

    def _new_pairs_with_new_parent(self, tainted_sigma1: TaintedLabel, new_tainted_sigma1: TaintedLabel, pairs: Iterable[TaintedPair], exclude_child: str | int | None = None) -> Iterable[TaintedPair]:
        for p in pairs:
            if p.parent == tainted_sigma1 and p.child_key != exclude_child:
                new_pair = self.tainted_pair_factory.replace(p, parent=new_tainted_sigma1)
                logger.debug(f"Generated new pair with new parent: ({self.label_name(new_pair.parent)}, {self.label_name(new_pair.child)}, {new_pair.child_key})")
                yield new_pair

    def _new_pairs_with_new_child(self, tainted_sigma1: TaintedLabel, new_tainted_sigma1: TaintedLabel, pairs: Iterable[TaintedPair]) -> Iterable[TaintedPair]:
        for p in pairs:
            if p.child == tainted_sigma1:
                new_pair = self.tainted_pair_factory.replace(p, child=new_tainted_sigma1)
                logger.debug(f"Generated new pair with new child: ({self.label_name(new_pair.parent)}, {self.label_name(new_pair.child)}, {new_pair.child_key})")
                yield new_pair

    def _new_pairs(
        self,
        tainted_sigma1: TaintedLabel,
        new_tainted_sigma1: TaintedLabel,
        pairs: Iterable[TaintedPair],
        exclude_dir: Dir | None = None,
    ) -> Iterable[TaintedPair]:
        """Generate new tainted pairs where new_tainted_sigma1 can be either the parent or the child"""
        logger.debug(f"exclude_dir = {exclude_dir}")
        logger.debug(f"tainted_sigma1: {self.label_name(tainted_sigma1)}")
        logger.debug(f"new_tainted_sigma1: {self.label_name(new_tainted_sigma1)}")
        # add a control for the direction
        exclude_child = exclude_dir.child if isinstance(exclude_dir, Down) else None
        pairs = tuple(pairs)
        yield from self._new_pairs_with_new_parent(tainted_sigma1, new_tainted_sigma1, pairs, exclude_child)
        if exclude_dir != Up():
            yield from self._new_pairs_with_new_child(tainted_sigma1, new_tainted_sigma1, pairs)

    def _internal_tainting_steps(self, taintd_sigma: TaintedLabel) -> Iterable[TaintingStep]:
        start_ptr_tainting = self._start_of_pointer_tainting(taintd_sigma)
        logger.debug(f"evaluating start of pointer tainting for {self.label_name(taintd_sigma)}")
        if start_ptr_tainting is not None:
            logger.debug(f"Start of pointer tainting for label: {self.label_name(taintd_sigma)} -> {self.label_name(start_ptr_tainting.new_lab)}")
            yield start_ptr_tainting
        else:
            logger.debug(f"Start of pointer tainting for {self.label_name(taintd_sigma)} failed")

        # internal pointer tainting propagation
        logger.debug(f"evaluating internal pointer tainting propagation for {self.label_name(taintd_sigma)}")
        internal_ptr_tainting_propagation = self._internal_ptr_taint_propagation(taintd_sigma)
        if internal_ptr_tainting_propagation is not None:
            logger.debug(f"Internal pointer tainting propagation for label: {self.label_name(taintd_sigma)} -> {self.label_name(internal_ptr_tainting_propagation.new_lab)}")
            yield internal_ptr_tainting_propagation
        else:
            logger.debug(f"Internal pointer tainting propagation for {self.label_name(taintd_sigma)} failed")

        # end of pointer tainting
        logger.debug(f"evaluating end of pointer tainting for {self.label_name(taintd_sigma)}")
        end_ptr_tainting = self._end_of_pointer_tainting(taintd_sigma)
        if end_ptr_tainting is not None:
            logger.debug(f"End of pointer tainting for label: {self.label_name(taintd_sigma)} -> {self.label_name(end_ptr_tainting.new_lab)}")
            yield end_ptr_tainting
        else:
            logger.debug(f"End of pointer tainting for {self.label_name(taintd_sigma)} failed")

    def _external_tainting_steps(self, tainted_pair: TaintedPair) -> Iterable[TaintingStep]:
        logger.debug(f"evaluating structural child tainting for pair: ({self.label_name(tainted_pair.parent)}, {self.label_name(tainted_pair.child)}, {tainted_pair.child_key})")
        structural_child_tainting = self._structural_child_tainting(tainted_pair)
        if structural_child_tainting is not None:
            logger.debug(f"strutural child tainting ({self.label_name(tainted_pair.parent)}, {self.label_name(tainted_pair.child)}, {tainted_pair.child_key})")
            logger.debug(f"parent: {self.label_name(structural_child_tainting.parent)}")
            logger.debug(f"child: {self.label_name(structural_child_tainting.child)}")
            logger.debug(f"new_child: {self.label_name(structural_child_tainting.new_child)}")
            yield structural_child_tainting

        # parent to j-th child pointer tainting propagation
        logger.debug(f"evaluating parent to j-th child pointer tainting propagation for pair: ({self.label_name(tainted_pair.parent)}, {self.label_name(tainted_pair.child)}, {tainted_pair.child_key})")
        parent_to_jth_child_ptr_tainting_propagation = self._parent_to_jth_child_ptr_taint_propagation(tainted_pair)
        if parent_to_jth_child_ptr_tainting_propagation is not None:
            logger.debug("parent to jth child")
            logger.debug(f"parent: {self.label_name(parent_to_jth_child_ptr_tainting_propagation.parent)}")
            logger.debug(f"child: {self.label_name(parent_to_jth_child_ptr_tainting_propagation.child)}")
            logger.debug(f"new_child: {self.label_name(parent_to_jth_child_ptr_tainting_propagation.new_child)}")

            yield parent_to_jth_child_ptr_tainting_propagation

        # child to parent pointer tainting propagation
        logger.debug(f"evaluating child to parent pointer tainting propagation for pair: ({self.label_name(tainted_pair.parent)}, {self.label_name(tainted_pair.child)}, {tainted_pair.child_key})")
        child_to_parent_ptr_tainting_propagation = self._child_to_parent_ptr_taint_propagation(tainted_pair)
        if child_to_parent_ptr_tainting_propagation is not None:
            logger.debug("child to parent")
            logger.debug(f"parent: {self.label_name(child_to_parent_ptr_tainting_propagation.parent)}")
            logger.debug(f"child: {self.label_name(child_to_parent_ptr_tainting_propagation.child)}")
            logger.debug(f"new_parent: {self.label_name(child_to_parent_ptr_tainting_propagation.new_parent)}")
            yield child_to_parent_ptr_tainting_propagation

    def consistent_taint(self, tainted_sigma1: TaintedLabel, i1: int, tainted_sigma2: TaintedLabel, i2: int, exclude_ptrs: set[str] = set()) -> bool:
        sigma2 = tainted_sigma2.label
        taint_ptr1 = tainted_sigma1.taint_ptr
        taint_ptr2 = tainted_sigma2.taint_ptr
        pointers = set(sigma2.frame.isnil.keys())

        for p in pointers.difference(exclude_ptrs):
            if (
                not any(last_assignment_to_field(sigma2, j, p, i2) for j in sigma2.frame.active_child.keys() if isinstance(j, str)) and
                taint_ptr2[p, i2]
            ):
                if not taint_ptr1[(p, i1)]:
                    logger.debug(f"Inconsistent tainting: pointer {p} is tainted in {self.label_name(tainted_sigma2)} at position {i2} but not in {self.label_name(tainted_sigma1)} at position {i1}")
                    return False

        return True

    def consistent_child_t(self, tainted_sigma: TaintedLabel, child_key: str|int, tainted_tau: TaintedLabel) -> bool:
        sigma = tainted_sigma.label
        tau = tainted_tau.label

        for frame in iter(tau): # step_down
            if frame.prev is None:
                continue
            b = frame.prev[1]
            a = frame.index
            if (
                frame.prev[0] == Up() and
                not self.consistent_taint(tainted_tau, a, tainted_sigma, b)
            ):
                return False

        for frame in iter(sigma): # step_up
            if frame.prev is None:
                continue
            b = frame.prev[1]
            a = frame.index
            if (
                frame.prev[0] == Down(child_key) and
                not self.consistent_taint(tainted_sigma, a, tainted_tau, b)
            ):
                return False

        return True

    def taint(self) -> tuple[set[TaintingStep], set[TaintedLabel], set[TaintedPair]]:
        internal_tainting_progress: defaultdict[TaintedLabel, set[TaintedLabel]] = defaultdict(set)
        pairs = set(map(lambda tup: Pair(*tup), self.trees.pairs()))
        L_Terminal, P_Terminal = generate_terminals(pairs, end_of_lace, lambda lab: lab.origin)  # noqa: N806
        logger.debug(f"Terminal labels: {len(L_Terminal)}")
        for lab in L_Terminal:
            logger.debug(f"Terminal label: {self.trees.id(lab)}")
        for pair in P_Terminal:
            logger.debug(f"Terminal pair: ({self.trees.id(pair.parent)}, {self.trees.id(pair.child)}, {pair.child_key})")
        db: TaintDB = TaintDB()

        tainting_steps: set[TaintingStep] = set()
        for term_lab in L_Terminal:
            tainted_lab = self._init_tainted_label(term_lab)
            db.add_label(tainted_lab)
            if end_of_lace(term_lab) and not term_lab.frame.isnil[self.root_name]:
                step = LookingForRoot(tainted_label=tainted_lab)
            else:
                step = TaintingInitialization(tainted_label=tainted_lab)
            tainting_steps.add(step)

        for p in P_Terminal:
            tainted_parent = self._init_tainted_label(p.parent)
            tainted_child = self._init_tainted_label(p.child)
            db.add_label(tainted_parent)
            db.add_label(tainted_child)
            tainted_pair = self.tainted_pair_factory.create(parent=tainted_parent, child=tainted_child, child_key=p.child_key)
            db.add_pair(tainted_pair)

        queue: deque[TaintedLabel | TaintedPair] = deque([*db.labels(), *db.pairs()])

        def on_new_label(tlab: TaintedLabel, new_tlab: TaintedLabel, exclude_dir: Dir | None = None) -> None:
            db.add_label(new_tlab)
            temp_P_tainted: set[TaintedPair] = set()  # noqa: N806
            queue.append(new_tlab)
            logger.debug(f"Updating new label: {self.label_name(new_tlab)} {f'excluding {exclude_dir}' if exclude_dir else ''}")
            for pair in db.get_involved_pairs(tlab):
                logger.debug(f"Involved pair: ({self.label_name(pair.parent)}, {self.label_name(pair.child)}, {pair.child_key})")
            for new_pair in self._new_pairs(tlab, new_tlab, db.get_involved_pairs(tlab), exclude_dir):
                logger.debug(f"Evaluating new pair after tainting: ({self.label_name(new_pair.parent)}, {self.label_name(new_pair.child)}, {new_pair.child_key})")

                if not db.contains_pair(new_pair):
                    logger.debug(f"Discovered new pair: ({self.label_name(new_pair.parent)}, {self.label_name(new_pair.child)}, {new_pair.child_key})")
                    if not self.consistent_child_t(tainted_sigma=new_pair.parent, child_key=new_pair.child_key, tainted_tau=new_pair.child):
                        logger.debug(f"Skipping inconsistent pair: ({self.label_name(new_pair.parent)}, {self.label_name(new_pair.child)}, {new_pair.child_key})")
                        continue
                    temp_P_tainted.add(new_pair)
                    queue.append(new_pair)
            for new_pair in temp_P_tainted:
                logger.debug(f"Adding new pair: ({self.label_name(new_pair.parent)}, {self.label_name(new_pair.child)}, {new_pair.child_key})")
                db.add_pair(new_pair)

        def on_new_parent(parent: TaintedLabel, new_parent: TaintedLabel, child: TaintedLabel, child_key: str | int) -> None:
            logger.debug("on_new_parent(parent={}, new_parent={}, child={}, child_key={}".format(self.label_name(parent), self.label_name(new_parent), self.label_name(child), child_key))
            on_new_label(parent, new_parent, exclude_dir=Down(child_key))
            new_pair = self.tainted_pair_factory.create(parent=new_parent, child=child, child_key=child_key)
            if not db.contains_pair(new_pair):
                logger.debug("Discovered new pair after up tainting propagation: ({}, {}, {})".format(self.label_name(new_parent), self.label_name(child), child_key))
                if not self.consistent_child_t(tainted_sigma=new_parent, child_key=child_key, tainted_tau=child):
                    logger.debug(f"Skipping inconsistent pair: ({self.label_name(new_parent)}, {self.label_name(child)}, {child_key})")
                    return
                logger.debug(f"Adding new special pair: ({self.label_name(new_parent)}, {self.label_name(child)}, {child_key})")
                db.add_pair(new_pair)
                queue.append(new_pair)

        def on_new_child(child: TaintedLabel, new_child: TaintedLabel, parent: TaintedLabel, child_key: str | int) -> None:
            on_new_label(child, new_child, exclude_dir=Up())
            new_pair = self.tainted_pair_factory.create(parent=parent, child=new_child, child_key=child_key)
            if not db.contains_pair(new_pair):
                if not self.consistent_child_t(tainted_sigma=parent, child_key=child_key, tainted_tau=new_child):
                    logger.debug(f"Skipping inconsistent pair: ({self.label_name(parent)}, {self.label_name(new_child)}, {child_key})")
                    return
                logger.debug(f"Adding new special pair: ({self.label_name(parent)}, {self.label_name(new_child)}, {child_key})")
                db.add_pair(new_pair)
                queue.append(new_pair)

        visited: set[TaintedLabel | TaintedPair] = set()

        while queue:
            tainted_object = queue.popleft()
            tainted_object_str = self.label_name(tainted_object) if isinstance(tainted_object, TaintedLabel) else f"({self.label_name(tainted_object.parent)}, {self.label_name(tainted_object.child)}, {tainted_object.child_key})"
            logger.debug(f"Extracting tainted object: {tainted_object_str}")
            if tainted_object in visited:
                if isinstance(tainted_object, TaintedLabel):
                    for progress in internal_tainting_progress[tainted_object]:
                        logger.debug(f"updating after visiting a label: {self.label_name(tainted_object)}; progress {self.label_name(progress)}")
                        on_new_label(tainted_object, progress)
                        queue.append(progress)
                continue
            visited.add(tainted_object)
            match tainted_object:
                case TaintedLabel() as tlab:
                    temp_tainting_steps = self._internal_tainting_steps(tlab)
                case TaintedPair() as tpair:
                    temp_tainting_steps = self._external_tainting_steps(tpair)
            for step in temp_tainting_steps:
                tainting_steps.add(step)
                match step:
                    case StructuralChildTainting(parent=parent, child=child, new_child=new_child, child_key=child_key):
                        on_new_child(child, new_child, parent, child_key)
                    case StartOfPointerTainting(lab=lab, new_lab=new_lab):
                        internal_tainting_progress[lab].add(new_lab)
                        on_new_label(lab, new_lab)
                    case InternalTaintingPropagation(lab=lab, new_lab=new_lab):
                        internal_tainting_progress[lab].add(new_lab)
                        on_new_label(lab, new_lab)
                    case UpTaintingPropagation(parent=parent, new_parent=new_parent, child=child, child_key=child_key):
                        logger.debug("updating after up tainting propagation")
                        on_new_parent(parent, new_parent, child, child_key)
                    case DownTaintingPropagation(child=child, new_child=new_child, parent=parent, child_key=child_key):
                        on_new_child(child, new_child, parent, child_key)
                    case PointerTaintingEnd(lab=lab, new_lab=new_lab):
                        internal_tainting_progress[lab].add(new_lab)
                        on_new_label(lab, new_lab)
                    case _:
                        assert False, "Unreachable branch"
                        pass
        return tainting_steps, set(db.labels()), set(db.pairs())
