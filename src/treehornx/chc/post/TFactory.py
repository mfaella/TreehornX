from dataclasses import dataclass, field
from itertools import product
from logging import Logger
from typing import Iterable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx.chc.computation.LabFactory import LabFactory
from treehornx.chc.post.helpers import last_assignment_to_field, no_assignment_to_field, ptr_here
from treehornx.chc.post.tainting import (
    DownTaintingPropagation,
    InternalTaintingPropagation,
    LookingForRoot,
    PointerTaintingEnd,
    StartOfPointerTainting,
    StructuralChildTainting,
    TaintedLabel,
    TaintedPair,
    TaintingInitialization,
    TaintingStep,
    UpTaintingPropagation,
)
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.enum_labels.core.Dir import Down, Internal, Up
from treehornx.enum_labels.core.Event import FieldAssignP, FieldHere, Here


@dataclass
class TFactory:
    lab_factory: LabFactory
    fragment_factory: CHCFragmentFactory = field(init=False)

    def __post_init__(self):
        self.fragment_factory = self.lab_factory.fragment_factory

    def label_name(self, tainted_label: TaintedLabel) -> str:
        taint_node_id = 1 if tainted_label.taint_node else 0
        taint_ptr = sorted(tainted_label.taint_ptr.items())
        taint_ptr_id = 0
        for _, is_tainted in taint_ptr:
            taint_ptr_id = (taint_ptr_id << 1) | is_tainted
        name = f"{self.fragment_factory.id_getter(tainted_label.label)}_{taint_node_id}_{taint_ptr_id}"
        return name

    def _predicate_name(self, tainted_label: TaintedLabel) -> str:
        label_name = self.label_name(tainted_label)
        name = f"T_{label_name}"
        # if name == "T_29_3":
        #     print(f"tainted_node: {tainted_label.taint_node}")
        #     print(f"tainted_pair: {tainted_label.taint_ptr}")

        return name

    def predicate(self, tainted_label: TaintedLabel) -> FNode:
        symbols = list(self.fragment_factory.label_symbols(tainted_label.label))
        arg_types = [sym.get_type() for sym in symbols]
        predicate_name = self._predicate_name(tainted_label)
        return chc.Predicate(predicate_name, arg_types)

    def apply(self, tainted_label: TaintedLabel, prefix: str = "") -> FNode:
        predicate = self.predicate(tainted_label)
        symbols = list(self.fragment_factory.label_symbols(tainted_label.label, prefix))
        return chc.Apply(predicate, symbols)

    def _T_looking_for_root(self, tainting_step: LookingForRoot) -> FNode:  # noqa: N802
        body = self.lab_factory.apply(tainting_step.tainted_label.label)
        head = self.apply(tainting_step.tainted_label)
        return chc.Clause(body, head)

    def _T_tainting_initialization(self, tainting_step: TaintingInitialization) -> FNode:  # noqa: N802
        body = self.lab_factory.apply(tainting_step.tainted_label.label)
        head = self.apply(tainting_step.tainted_label)
        return chc.Clause(body, head)

    def _T_structural_child_tainting(self, tainting_step: StructuralChildTainting) -> FNode:  # noqa: N802
        sigma_app = self.apply(tainting_step.parent, prefix="p")
        tau_app = self.apply(tainting_step.child, prefix="c")
        constraints = self.fragment_factory.cross_data_constraints(
            tainting_step.parent.label,
            tainting_step.child.label,
            tainting_step.child_key,
            parent_variable_prefix="p",
            child_variable_prefix="c",
        )
        body = smt.And(sigma_app, tau_app, *constraints)
        head = self.apply(tainting_step.new_child, prefix="c")
        return chc.Clause(body, head)

    def _T_start_of_pointer_tainting(self, tainting_step: StartOfPointerTainting) -> FNode:  # noqa: N802
        body = self.apply(tainting_step.lab)
        head = self.apply(tainting_step.new_lab)
        return chc.Clause(body, head)

    def _T_internal_tainting_propagation(self, tainting_step: InternalTaintingPropagation) -> FNode:  # noqa: N802
        body = self.apply(tainting_step.lab)
        head = self.apply(tainting_step.new_lab)
        assert tainting_step.new_lab.label is tainting_step.lab.label
        return chc.Clause(body, head)

    def _T_up_tainting_propagation(self, tainting_step: UpTaintingPropagation) -> FNode:  # noqa: N802
        parent_app = self.apply(tainting_step.parent, prefix="p")
        child_app = self.apply(tainting_step.child, prefix="c")
        constraints = self.fragment_factory.cross_data_constraints(
            tainting_step.parent.label,
            tainting_step.child.label,
            tainting_step.child_key,
            parent_variable_prefix="p",
            child_variable_prefix="c",
        )
        body = smt.And(parent_app, child_app, *constraints)
        head = self.apply(tainting_step.new_parent, prefix="p")
        return chc.Clause(body, head)

    def _T_down_tainting_propagation(self, tainting_step: DownTaintingPropagation) -> FNode:  # noqa: N802
        parent_app = self.apply(tainting_step.parent, prefix="p")
        child_app = self.apply(tainting_step.child, prefix="c")
        constraints = self.fragment_factory.cross_data_constraints(
            tainting_step.parent.label,
            tainting_step.child.label,
            tainting_step.child_key,
            parent_variable_prefix="p",
            child_variable_prefix="c",
        )
        body = smt.And(parent_app, child_app, *constraints)
        head = self.apply(tainting_step.new_child, prefix="c")
        return chc.Clause(body, head)

    def _T_pointer_tainting_end(self, tainting_step: PointerTaintingEnd) -> FNode:  # noqa: N802
        body = self.apply(tainting_step.lab)
        head = self.apply(tainting_step.new_lab)
        assert tainting_step.new_lab.label is tainting_step.lab.label
        return chc.Clause(body, head)

    def T(self, tainting_step: TaintingStep) -> FNode:  # noqa: N802
        match tainting_step:
            case LookingForRoot():
                clause = self._T_looking_for_root(tainting_step)
            case TaintingInitialization():
                clause = self._T_tainting_initialization(tainting_step)
            case StructuralChildTainting():
                clause = self._T_structural_child_tainting(tainting_step)
            case StartOfPointerTainting():
                clause = self._T_start_of_pointer_tainting(tainting_step)
            case InternalTaintingPropagation():
                clause = self._T_internal_tainting_propagation(tainting_step)
            case UpTaintingPropagation():
                clause = self._T_up_tainting_propagation(tainting_step)
            case DownTaintingPropagation():
                clause = self._T_down_tainting_propagation(tainting_step)
            case PointerTaintingEnd():
                clause = self._T_pointer_tainting_end(tainting_step)

        return clause

    def _query_1(self, tainted_label: TaintedLabel) -> FNode | None:
        taint_ptr = tainted_label.taint_ptr
        for (p1, i1), (p2, i2) in product(
            tainted_label.taint_ptr.keys(),
            tainted_label.taint_ptr.keys(),
        ):
            if p1 == p2:
                continue

            if not taint_ptr[(p1, i1)]:
                continue

            if not taint_ptr[(p2, i2)]:
                continue

            if not ptr_here(tainted_label.label, i1, p1):
                continue

            if not ptr_here(tainted_label.label, i2, p2):
                continue

            body = self.apply(tainted_label)
            head = smt.FALSE()
            return chc.Clause(body, head)

        return None

    def _query_2_internal(self, tlabel: TaintedLabel) -> FNode | None:
        taint_ptr = tlabel.taint_ptr
        taint_node = tlabel.taint_node
        sigma2 = tlabel.label

        if not taint_node:
            return None

        for p, i2 in taint_ptr.keys():
            sigma2_i2_prev = sigma2[i2].prev
            assert sigma2_i2_prev is not None
            if sigma2_i2_prev[0] != Internal():
                continue

            if not taint_ptr[(p, i2)]:
                continue

            if ptr_here(sigma2, i2, p):
                continue

            i1 = sigma2_i2_prev[1]
            sigma1 = sigma2

            for child_key in sigma2.frame.active_child.keys():
                if isinstance(child_key, int):
                    continue

                if last_assignment_to_field(sigma1, child_key, p, i1):
                    body = self.apply(tlabel)
                    head = smt.FALSE()
                    return chc.Clause(body, head)

        return None

    def _query_2_up(self, tpair: TaintedPair) -> FNode | None:
        t_sigma1 = tpair.parent
        t_sigma2 = tpair.child
        sigma1 = t_sigma1.label
        sigma2 = t_sigma2.label
        child_key = tpair.child_key
        taint_ptr2 = t_sigma2.taint_ptr
        taint_node1 = t_sigma1.taint_node

        if not taint_node1:
            return None

        for p, i2 in taint_ptr2.keys():
            sigma2_i2_prev = sigma2[i2].prev
            assert sigma2_i2_prev is not None
            if sigma2_i2_prev[0] != Up():
                continue

            if not taint_ptr2[(p, i2)]:
                continue

            if ptr_here(sigma2, i2, p):
                continue

            i1 = sigma2_i2_prev[1]

            for child_key in sigma2.frame.active_child.keys():
                if isinstance(child_key, int):
                    continue

                # In the paper the condition includes only last_assignment_to_field. This query specifically check if a pointer is tainted (the search for that pointer is started)
                # and the backwarding search encounter a field of another node which has been last assigned to the same pointer and in the meantime the pointer is not been updated.
                # Since in the compressed encoding all the events consecutively executed on the same node are merged into a single set of events, it's not enough to check that a pointer is been assigned to that field,
                # but also that the pointer is not been uppdated int the meantime. Checking "Here(p) not in frame.events" it is enough to ensure that the pointer is been updated after being assigned to the field.
                # Otherwise the pointer would point to the current node and the events set would contain FieldHere(pfield) instead of FieldAssignP(pfield, p) which is automatically discarded by last_assignemnt_to_field.
                if last_assignment_to_field(sigma1, child_key, p, i1) and Here(p) not in sigma1.frame.events:
                    sigma1_app = self.apply(t_sigma1, prefix="p")
                    sigma2_app = self.apply(t_sigma2, prefix="c")
                    constraints = self.fragment_factory.cross_data_constraints(
                        sigma1,
                        sigma2,
                        child_key,
                        parent_variable_prefix="p",
                        child_variable_prefix="c",
                    )
                    body = smt.And(sigma1_app, sigma2_app, *constraints)
                    head = smt.FALSE()
                    return chc.Clause(body, head)

        return None

    def _query_2_down(self, tpair: TaintedPair) -> FNode | None:
        t_sigma1 = tpair.child
        t_sigma2 = tpair.parent
        sigma1 = t_sigma1.label
        sigma2 = t_sigma2.label
        child_key = tpair.child_key
        taint_ptr2 = t_sigma2.taint_ptr
        taint_node1 = t_sigma1.taint_node

        if not taint_node1:
            return None

        for p, i2 in taint_ptr2.keys():
            sigma2_i2_prev = sigma2[i2].prev
            assert sigma2_i2_prev is not None
            if sigma2_i2_prev[0] != Down(child_key):
                continue

            if not taint_ptr2[(p, i2)]:
                continue

            if ptr_here(sigma2, i2, p):
                continue

            i1 = sigma2_i2_prev[1]

            for child_key in sigma2.frame.active_child.keys():
                if isinstance(child_key, int):
                    continue

                if last_assignment_to_field(sigma1, child_key, p, i1) and Here(p) not in sigma1.frame.events:
                    sigma1_app = self.apply(t_sigma1, prefix="c")
                    sigma2_app = self.apply(t_sigma2, prefix="p")
                    constraints = self.fragment_factory.cross_data_constraints(
                        sigma2,
                        sigma1,
                        child_key,
                        parent_variable_prefix="p",
                        child_variable_prefix="c",
                    )
                    body = smt.And(sigma1_app, sigma2_app, *constraints)
                    head = smt.FALSE()
                    return chc.Clause(body, head)

        return None

    def _query_3(self, tpair: TaintedPair) -> FNode | None:
        t_sigma = tpair.parent
        t_tau = tpair.child
        sigma = t_sigma.label
        tau = t_tau.label
        taint_ptr2 = t_tau.taint_ptr
        child_key = tpair.child_key

        if not t_sigma.taint_node:
            return None

        if isinstance(child_key, int):
            return None

        if not no_assignment_to_field(sigma, child_key):
            return None

        for p, i in taint_ptr2.keys():
            if not taint_ptr2[(p, i)]:
                continue

            if not ptr_here(tau, i, p):
                continue

            if not tau.frame.active:
                continue

            sigma_app = self.apply(t_sigma, prefix="p")
            tau_app = self.apply(t_tau, prefix="c")
            constraints = self.fragment_factory.cross_data_constraints(
                sigma,
                tau,
                child_key,
                parent_variable_prefix="p",
                child_variable_prefix="c",
            )
            body = smt.And(sigma_app, tau_app, *constraints)
            head = smt.FALSE()
            return chc.Clause(body, head)

        return None

    def _child_points_here(self, t_lab: TaintedLabel, child_name: str) -> bool:
        for frame in reversed(t_lab.label):
            if frame.events.intersection({FieldHere(child_name)}):
                return True
            if any(isinstance(e, FieldAssignP) and e.pfield == child_name for e in frame.events):
                return False
        return False

    def _query_4(self, t_lab: TaintedLabel) -> FNode | None:
        if not t_lab.taint_node:
            return None

        for child_key in t_lab.label.frame.active_child.keys():
            if isinstance(child_key, int):
                continue

            if self._child_points_here(t_lab, child_key):
                body = self.apply(t_lab)
                head = smt.FALSE()
                return chc.Clause(body, head)

        return None

    def query(self, tainted_object: TaintedLabel | TaintedPair) -> Iterable[FNode]:
        match tainted_object:
            case TaintedLabel() as tlab:
                if q := self._query_1(tlab):
                    yield q
                if q := self._query_2_internal(tlab):
                    yield q
                if q := self._query_4(tlab):
                    yield q
            case TaintedPair() as tpair:
                if q := self._query_2_up(tpair):
                    yield q
                if q := self._query_2_down(tpair):
                    yield q
                if q := self._query_3(tpair):
                    yield q
