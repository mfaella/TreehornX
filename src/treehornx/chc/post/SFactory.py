

from dataclasses import dataclass, field, replace
from functools import cached_property
from itertools import product
from typing import Iterable

from frozendict import frozendict
from loguru import logger
from pysmt.fnode import FNode
import pysmt.shortcuts as smt
import pysmt.typing as smtty

from treehornx.chc.computation.LabFactory import LabFactory
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.helpers import last_assignment_to_field, child_is_dflt, ptr_here
from treehornx.chc.post.sainting.core import Q, Acceptance, AutomataTransition, DownStatePropagation, Initialization, InternalStatePropagation, SaintedLabel, SaintingStep, StartStatePropagation, UpStatePropagation
from treehornx.chc.post.sainting.helpers import missing_child
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Down, Up
from treehornx.enum_labels.core.Label import Label
from treehornx.chc.SDTAContext import SDTAContext
import pychc.shortcuts as chc

@dataclass
class SFactory:

    trees: KnittedTrees
    sdta_ctx: SDTAContext
    t_factory: TFactory
    lab_factory: LabFactory = field(init=False)
    fragment_factory: CHCFragmentFactory = field(init=False)

    def __post_init__(self):
        self.lab_factory = self.t_factory.lab_factory
        self.fragment_factory = self.lab_factory.fragment_factory
        self._automata_transition_cache: dict[tuple[SaintedLabel, frozendict[str, SaintedLabel]], FNode] = dict()

    @cached_property
    def states_name(self) -> tuple[str, ...]:
        return tuple(self.sdta_ctx.states)

    def label_name(self, sainted_label: SaintedLabel) -> str:
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
        return name

    def _predicate_name(self, sainted_label: SaintedLabel) -> str:
        slab_name = self.label_name(sainted_label)
        predicate_name = f"S_{slab_name}"
        return predicate_name

    def _state_symbol_name(self, sainted_label: SaintedLabel, state_name: str, prefix: str = "") -> str:
        if prefix != '':
            prefix = f"{prefix}_"
        slab_name = self.label_name(sainted_label)
        return f"{prefix}{state_name}_{slab_name}"

    def _state_symbol(self, sainted_label: SaintedLabel, state_name: str, prefix: str = "") -> FNode:
        symbol_name = self._state_symbol_name(sainted_label, state_name, prefix)
        type = smtty.INT if self.sdta_ctx.states[state_name] == 'int' else smtty.BOOL
        symbol = smt.Symbol(symbol_name, type)
        return symbol

    def _ptr_state_symbol_with_coordinates(self, sainted_label: SaintedLabel, state_name: str, coordinates: tuple[str, int], prefix: str = "") -> FNode:
        if prefix != "":
            prefix = f"{prefix}_"
        prefix = f"{prefix}{coordinates[0]}_{coordinates[1]}"
        symbol = self._state_symbol(sainted_label, state_name, prefix)
        return symbol

    def _ptr_state_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        for (p, i), state in sorted(sainted_label.state_ptr.items()):
            if state == Q():
                for state_name in self.states_name:
                     yield self._ptr_state_symbol_with_coordinates(sainted_label, state_name, (p, i), prefix)

    def _node_state_symbol(self, sainted_label: SaintedLabel, state_name: str, prefix: str = "") -> FNode:
        if prefix != "":
            prefix = f"{prefix}_qnode"
        else:
            prefix = "qnode"
        return self._state_symbol(sainted_label, state_name, prefix)

    def _node_state_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:

        state_node = sainted_label.state_node
        assert isinstance(state_node, Q)
        for state_name in self.states_name:
            yield self._node_state_symbol(sainted_label, state_name, prefix)

    def _predicate_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        yield from self.fragment_factory.label_symbols(sainted_label.label, prefix)
        yield from self.aux_symbols(sainted_label, prefix)

    def predicate(self, label: SaintedLabel) -> FNode:
        arg_types = [sym.get_type() for sym in self._predicate_symbols(label)]
        pred_name = self._predicate_name(label)
        predicate = chc.Predicate(pred_name, arg_types)
        return predicate

    def apply(self, sainted_label: SaintedLabel, var_prefix: str = "") -> FNode:
        predicate = self.predicate(sainted_label)
        symbols = list(self._predicate_symbols(sainted_label, prefix=var_prefix))
        return chc.Apply(predicate, symbols)

    def _initialization(self, step: Initialization) -> FNode:
        body = self.t_factory.apply(step.tainted_label)
        head = self.apply(step.sainted_label)
        clause = chc.Clause(body, head)
        return clause

    def _automata_transition(self, step: AutomataTransition) -> FNode:
        logger.debug(f"Processing automata transition clause on {self.label_name(step.parent)} to {self.label_name(step.new_parent)} with children {[child_key for child_key in step.states_source.keys()]}")
        child_states: dict[str, dict[str, FNode]|None] = dict()
        conjuncts: list[FNode] = []
        parent_prefix = "p"
        for index, (child_key, state_src) in enumerate(step.states_source.items()):
            child_prefix = f"c{index}"
            match state_src:
                case None:
                    logger.debug(f"Automata transition step: child {child_key} has no state source")
                    child_states[child_key] = None
                case (p, i):
                    logger.debug(f"Automata transition step: child {child_key} has state source coordinates {(p, i)}")
                    states = dict(zip(
                        self.states_name,
                        (
                            self._ptr_state_symbol_with_coordinates(step.parent, state_name, (p, i), prefix=parent_prefix)
                            for state_name in self.states_name
                        )
                    ))
                    child_states[child_key] = states
                case SaintedLabel() as child_sainted_label:
                    conjuncts.append(self.apply(child_sainted_label,var_prefix=child_prefix))
                    conjuncts.extend(
                        self.fragment_factory.cross_data_constraints(
                            step.parent.label,
                            child_sainted_label.label,
                            child_key,
                            parent_variable_prefix=parent_prefix,
                            child_variable_prefix=child_prefix
                    ))
                    conjuncts.append(self.consistent_child_S(step.parent, child_key, child_sainted_label, sigma_var_prefix=parent_prefix, tau_var_prefix=child_prefix))
                    states = dict(zip(
                        self.states_name,
                        self._node_state_symbols(child_sainted_label, prefix=child_prefix)
                    ))
                    child_states[child_key] = states

        fields: dict[str, FNode] = dict()
        logger.debug(f"Automata transition children states: {child_states}")
        for field in self.fragment_factory.data_fields:
            if field.sort.is_enum() or field.sort.is_ptr():
                continue
            symbol = self.fragment_factory.field_symbol(field, step.parent.label, prefix=parent_prefix)
            fields[field.name] = symbol

        enum_fields: dict[str, str] = dict(step.parent.label.frame.enum_fields)

        parent_states = dict(zip(
            self.states_name,
            self._node_state_symbols(step.new_parent, prefix=parent_prefix)
        ))

        psi = self.sdta_ctx.psi(
            child_states,
            fields,
            enum_fields,
            parent_states
        )

        logger.debug(f"psi: {psi}")

        body = smt.And(
            self.apply(step.parent, "p"),
            psi,
            *conjuncts,
            *self._internal_ptr_state_equalities(step.parent, step.new_parent, prefix=parent_prefix)
        )

        head = self.apply(step.new_parent, var_prefix=parent_prefix)
        clause = chc.Clause(body, head)
        logger.debug(f"clause: {clause.serialize()}")
        return clause

    def _ptr_state_equalities(self, src_sainted_label: SaintedLabel, dest_sainted_label: SaintedLabel, updates: Iterable[tuple[str, int, int]], src_prefix: str = "", dest_prefix: str = "") -> Iterable[FNode]:
        for state_name in self.sdta_ctx.states:
            for (p, i, j) in updates:
                src_symbol = self._ptr_state_symbol_with_coordinates(src_sainted_label, state_name, (p, i), src_prefix)
                dest_symbol = self._ptr_state_symbol_with_coordinates(dest_sainted_label, state_name, (p, j), dest_prefix)
                yield smt.EqualsOrIff(src_symbol, dest_symbol)

    def _internal_ptr_state_equalities(self, src_sainted_label: SaintedLabel, dest_sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        for state_name in self.sdta_ctx.states:
            for (p, i), state in src_sainted_label.state_ptr.items():
                if state == Q():
                    src_symbol = self._ptr_state_symbol_with_coordinates(src_sainted_label, state_name, (p, i), prefix)
                    dest_symbol = self._ptr_state_symbol_with_coordinates(dest_sainted_label, state_name, (p, i), prefix)
                    yield smt.EqualsOrIff(src_symbol, dest_symbol)

    def _internal_node_state_equalities(self, src_sainted_label: SaintedLabel, dest_sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        for state_name in self.states_name:
            src_symbol = self._node_state_symbol(src_sainted_label, state_name, prefix)
            dest_symbol = self._node_state_symbol(dest_sainted_label, state_name, prefix)
            yield smt.EqualsOrIff(src_symbol, dest_symbol)

    def _start_of_state_propagation(self, step: StartStatePropagation) -> FNode:
        equalities: list[FNode] = []
        for coordinates in step.propagation_coordinates:
            for state_name in self.sdta_ctx.states:
                src_symbol = self._node_state_symbol(step.sainted_label, state_name)
                dest_symbol = self._ptr_state_symbol_with_coordinates(step.new_sainted_label, state_name, coordinates)
                equalities.append(smt.EqualsOrIff(src_symbol, dest_symbol))
        node_state_equalities = list(self._internal_node_state_equalities(step.sainted_label, step.new_sainted_label))
        ptr_state_equalities = list(self._internal_ptr_state_equalities(step.sainted_label, step.new_sainted_label))
        body = smt.And(
            self.apply(step.sainted_label),
            *equalities,
            *node_state_equalities,
            *ptr_state_equalities
        )
        head = self.apply(step.new_sainted_label)
        clause = chc.Clause(body, head)
        return clause

    def _internal_state_propagation(self, step: InternalStatePropagation) -> FNode:
        internal_node_state_eq = []
        if step.sainted_sigma.state_node == Q():
            internal_node_state_eq = list(self._internal_node_state_equalities(step.sainted_sigma, step.new_sainted_sigma))
        internal_ptr_state_eq = list(self._internal_ptr_state_equalities(step.sainted_sigma, step.new_sainted_sigma))
        body = smt.And(
            self.apply(step.sainted_sigma),
            *self._ptr_state_equalities(step.sainted_sigma, step.new_sainted_sigma, step.prpagations),
            *self._ptr_state_equalities(step.new_sainted_sigma, step.new_sainted_sigma, step.prpagations), # self-propagation of the updated ptr states
            *internal_node_state_eq,
            *internal_ptr_state_eq
        )
        head = self.apply(step.new_sainted_sigma)
        clause = chc.Clause(body, head)
        return clause

    def _up_state_propagation(self, step: UpStatePropagation) -> FNode:
        equalities = list(self._ptr_state_equalities(step.child, step.new_sainted_sigma2, step.prpagations, src_prefix="c", dest_prefix="p"))
        equalities.extend(self._internal_node_state_equalities(step.parent, step.new_sainted_sigma2, prefix="p"))
        equalities.extend(self._internal_ptr_state_equalities(step.parent, step.new_sainted_sigma2, prefix="p"))
        cross_data_constraints = self.fragment_factory.cross_data_constraints(
            step.parent.label,
            step.child.label,
            step.child_key,
            parent_variable_prefix="p",
            child_variable_prefix="c"
        )
        body = smt.And(
            self.apply(step.child, var_prefix="c"),
            self.apply(step.parent, var_prefix="p"),
            *equalities,
            *cross_data_constraints
        )
        head = self.apply(step.new_sainted_sigma2, var_prefix="p")
        clause = chc.Clause(body, head)
        return clause

    def _down_state_propagation(self, step: DownStatePropagation) -> FNode:
        equalities = list(self._ptr_state_equalities(step.sainted_sigma2, step.new_sainted_sigma2, step.prpagations, src_prefix="p", dest_prefix="c"))
        equalities.extend(self._internal_node_state_equalities(step.sainted_sigma2, step.new_sainted_sigma2, prefix="c"))
        equalities.extend(self._internal_ptr_state_equalities(step.sainted_sigma2, step.new_sainted_sigma2, prefix="c"))
        cross_data_constraints = self.fragment_factory.cross_data_constraints(
            step.parent.label,
            step.sainted_sigma2.label,
            step.child_key,
            parent_variable_prefix="p",
            child_variable_prefix="c"
        )
        body = smt.And(
            self.apply(step.parent, var_prefix="p"),
            self.apply(step.sainted_sigma2, var_prefix="c"),
            *equalities,
            *cross_data_constraints
        )
        head = self.apply(step.new_sainted_sigma2, var_prefix="c")
        clause = chc.Clause(body, head)
        return clause

    def _acceptance(self, step: Acceptance) -> FNode:
        body = smt.And(
            self.apply(step.sainted_label),
            self.apply_psiF(step.sainted_label)
        )
        head = smt.FALSE()
        clause = chc.Clause(body, head)
        return clause

    def consistent_state(self, sainted_sigma: SaintedLabel, i1: int, sainted_tau: SaintedLabel, i2: int, exclude_ptrs: set[str] = set(), var_prefix1: str = "", var_prefix2: str = "") -> FNode:
        sigma = sainted_sigma.label
        tau = sainted_tau.label
        ptr_states1 = sainted_sigma.state_ptr
        ptr_states2 = sainted_tau.state_ptr
        child_keys = list(j for j in sigma.frame.active_child.keys() if isinstance(j, str))
        pointers = set(sigma.frame.isnil.keys())
        state_consistency_constraints: list[FNode] = []
        for p in pointers.difference(exclude_ptrs):
            if not any((last_assignment_to_field(sigma, j, p, i1) for j in child_keys)) and isinstance(ptr_states1[p, i1], Q):
                if not isinstance(ptr_states2[p, i2], Q):
                    continue

                for state_name in self.states_name:
                    state_symbol1 = self._ptr_state_symbol_with_coordinates(sainted_sigma, state_name, (p, i1), var_prefix1)
                    state_symbol2 = self._ptr_state_symbol_with_coordinates(sainted_tau, state_name, (p, i2), var_prefix2)
                    state_consistency_constraints.append(smt.EqualsOrIff(state_symbol1, state_symbol2))

        return smt.And(*state_consistency_constraints)

    def consistent_child_S(self, sainted_sigma: SaintedLabel, child_key: str | int, sainted_tau: SaintedLabel, sigma_var_prefix: str, tau_var_prefix: str) -> FNode:
        sigma = sainted_sigma.label
        tau = sainted_tau.label
        lab_consistency_constraints = self.fragment_factory.cross_data_constraints(
            sainted_sigma.label,
            sainted_tau.label,
            child_key,
            parent_variable_prefix=sigma_var_prefix,
            child_variable_prefix=tau_var_prefix
        )
        state_consistency_constraints: list[FNode] = []
        for frame in iter(sigma):
            if frame.prev and frame.prev[0] == Down(child_key): # step_up
                a = frame.prev[1]
                b = frame.index
                state_consistency_constraints.append(self.consistent_state(sainted_tau, a, sainted_sigma, b, var_prefix1=tau_var_prefix, var_prefix2=sigma_var_prefix))

        for frame in iter(tau):
            if frame.prev and frame.prev[0] == Up(): # step_down
                a = frame.prev[1]
                b = frame.index
                state_consistency_constraints.append(self.consistent_state(sainted_sigma, a, sainted_tau, b, var_prefix1=sigma_var_prefix, var_prefix2=tau_var_prefix))

        return smt.And(*lab_consistency_constraints, *state_consistency_constraints)

    def apply_psiF(self, sainted_label: SaintedLabel, var_prefix: str = "") -> FNode:
        if sainted_label.state_node != Q():
            return smt.FALSE()
        if not any(
            v is True and ptr_here(sainted_label.label, i, p)
            for (p, i), v in sainted_label.state_ptr.items()
        ):
            return smt.FALSE()
        states_dict = dict(zip(self.sdta_ctx.states.keys(), self._node_state_symbols(sainted_label, var_prefix)))
        psif = self.sdta_ctx.psiF(states_dict)
        return psif

    def aux_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        if sainted_label.state_node == Q():
            yield from self._node_state_symbols(sainted_label, prefix)
        yield from self._ptr_state_symbols(sainted_label, prefix)

    def _non_structural_child_ready_for_transition(self, sainted_label: SaintedLabel, field_key: str) -> tuple[str, int]|None:
        ptrs = sainted_label.label.frame.isnil.keys()
        indices = range(len(sainted_label.label))
        for p, i in product(ptrs, indices):
            if last_assignment_to_field(sainted_label.label, field_key, p, i) and sainted_label.state_ptr[(p, i)] == Q():
                return (p, i)
        return None

    def automata_transition_constraints(self, sainted_parent: SaintedLabel, sainted_children: Iterable[tuple[str|int, SaintedLabel]]) -> FNode:
        if sainted_parent.state_node != Q():
            return smt.FALSE()
        # Do not consider aux children in the knitted trees since it only refers to node pointed by pointer fields in the node signature
        sainted_children = list(sainted_children)
        children_dict: dict[str, SaintedLabel | None] = dict()
        states_source: dict[str, None|tuple[str, int]|SaintedLabel] = dict()
        ready_for_transition = True
        for child_key, child in sainted_children:

            if isinstance(child_key, int):
                continue

            if missing_child(sainted_parent.label, child_key):
                children_dict[child_key] = None
                states_source[child_key] = None

            elif child_is_dflt(sainted_parent.label, child_key) and child.state_node == Q():
                children_dict[child_key] = child
                states_source[child_key] = child

            elif (coordinates := self._non_structural_child_ready_for_transition(sainted_parent, child_key)):
                children_dict[child_key] = None
                states_source[child_key] = coordinates

            else:
                ready_for_transition = False
                break

        if not ready_for_transition:
            return smt.FALSE()

        parent_prefix = "p"
        child_states: dict[str, dict[str, FNode]|None] = dict()
        for index, (child_key, _) in enumerate(sainted_children):
            if isinstance(child_key, int):
                continue
            child_prefix = f"c{index}"
            match states_source[child_key]:
                case None:
                    child_states[child_key] = None
                case (p, i):
                    states = dict(zip(
                        self.states_name,
                        (self._ptr_state_symbol_with_coordinates(sainted_parent, state_name, (p, i), prefix=parent_prefix) for state_name in self.states_name)
                    ))
                    child_states[child_key] = states
                case SaintedLabel() as child_sainted_label:
                    symbols = self._node_state_symbols(child_sainted_label, prefix=child_prefix)
                    states = dict(zip(
                        self.states_name,
                        symbols
                    ))
                    child_states[child_key] = states

        fields: dict[str, FNode] = dict()
        for field in self.fragment_factory.data_fields:
            if field.sort.is_enum() or field.sort.is_ptr():
                continue
            symbol = self.fragment_factory.field_symbol(field, sainted_parent.label, prefix=parent_prefix)
            fields[field.name] = symbol

        enum_fields: dict[str, str] = dict(sainted_parent.label.frame.enum_fields)

        parent_states = dict(zip(
            self.states_name,
            self._node_state_symbols(sainted_parent, prefix=parent_prefix)
        ))

        psi = self.sdta_ctx.psi(
            child_states,
            fields,
            enum_fields,
            parent_states
        )

        return psi


    def S(self, step: SaintingStep) -> FNode: # noqa: N802
        match step:
            case Initialization() as initialization:
                return self._initialization(initialization)
            case AutomataTransition() as automaton_transition:
                return self._automata_transition(automaton_transition)
            case StartStatePropagation() as start_state_propagation:
                return self._start_of_state_propagation(start_state_propagation)
            case InternalStatePropagation() as internal_state_propagation:
                return self._internal_state_propagation(internal_state_propagation)
            case UpStatePropagation() as up_state_propagation:
                return self._up_state_propagation(up_state_propagation)
            case DownStatePropagation() as down_state_propagation:
                return self._down_state_propagation(down_state_propagation)
            case Acceptance() as acceptance:
                return self._acceptance(acceptance)

    def all_S(self, steps: Iterable[SaintingStep]) -> Iterable[FNode]: # noqa: N802
        return map(self.S, steps)
