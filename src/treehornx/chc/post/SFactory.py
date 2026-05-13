

from dataclasses import dataclass, field
from functools import cached_property
from typing import Iterable

from pysmt.fnode import FNode
import pysmt.shortcuts as smt
import pysmt.typing as smtty

from treehornx.chc.computation.LabFactory import LabFactory
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.sainting.core import Q, Acceptance, AutomataTransition, DownStatePropagation, Initialization, InternalStatePropagation, SaintedLabel, SaintingStep, StartStatePropagation, UpStatePropagation
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.enum_labels import KnittedTrees
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

    @cached_property
    def states_name(self) -> tuple[str, ...]:
        return tuple(self.sdta_ctx.states)

    def _label_name(self, sainted_label: SaintedLabel) -> str:
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
        slab_name = self._label_name(sainted_label)
        predicate_name = f"S_{slab_name}"
        return predicate_name

    def _state_symbol_name(self, sainted_label: SaintedLabel, state_name: str, prefix: str = "") -> str:
        if prefix != '':
            prefix = f"{prefix}_"
        slab_name = self._label_name(sainted_label)
        return f"{prefix}{state_name}_{slab_name}"

    def _state_symbol(self, sainted_label: SaintedLabel, state_name: str, prefix: str = "") -> FNode:
        symbol_name = self._state_symbol_name(sainted_label, state_name, prefix)
        type = smtty.INT if self.sdta_ctx.states[state_name] == 'int' else smtty.BOOL
        symbol = smt.Symbol(symbol_name, type)
        return symbol

    def _ptr_state_symbol_with_coordinates(self, sainted_label: SaintedLabel, state_name: str, coordinates: tuple[str, int], prefix: str = "") -> FNode:
        if prefix != "":
            prefix = f"{prefix}_"
        symbol_name = f"{prefix}{state_name}_{coordinates[0]}_{coordinates[1]}"
        symbol = self._state_symbol(sainted_label, symbol_name, prefix)
        return symbol

    def _ptr_state_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        for (p, i), state in sorted(sainted_label.state_ptr.items()):
            if isinstance(state, Q):
                for state_name in self.states_name:
                     yield self._ptr_state_symbol_with_coordinates(sainted_label, state_name, (p, i), prefix)

    def _node_state_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:

        state_node = sainted_label.state_node
        assert isinstance(state_node, Q)
        if prefix != "":
            prefix = f"{prefix}_qnode"
        else:
            prefix = "qnode"
        for state_name in self.states_name:
            yield self._state_symbol(sainted_label, state_name, prefix)

    def _predicate_symbols(self, sainted_label: SaintedLabel, prefix: str = "") -> Iterable[FNode]:
        yield from self.fragment_factory.label_symbols(sainted_label.label, prefix)
        yield from self._node_state_symbols(sainted_label, prefix)
        yield from self._ptr_state_symbols(sainted_label, prefix)

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

    def _automaton_transition(self, step: AutomataTransition) -> FNode:
        child_states: dict[str, dict[str, FNode]|None] = dict()
        conjuncts: list[FNode] = []
        parent_prefix = "p"
        for index, (child_key, state_src) in enumerate(step.states_source):
            child_prefix = f"c{index}"
            match step.states_source[state_src]:
                case None:
                    child_states[child_key] = None
                case (p, i):
                    child_sainted_label = step.children[child_key]
                    assert child_sainted_label
                    symbols = (
                        self._ptr_state_symbol_with_coordinates(
                            child_sainted_label,
                            state_name,
                            (p, i),
                            prefix=child_prefix
                        )
                        for state_name in self.states_name
                    )
                    states = dict(zip(
                        self.states_name,
                        (self._ptr_state_symbol_with_coordinates(child_sainted_label, state_name, (p, i), prefix=child_prefix) for state_name in self.states_name)
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
                    symbols = (
                        self._state_symbol(child_sainted_label, state_name, prefix=child_prefix)
                        for state_name in self.states_name
                    )
                    states = dict(zip(
                        self.states_name,
                        symbols
                    ))
                    child_states[child_key] = states

        fields: dict[str, FNode] = dict()
        for field in self.fragment_factory.data_fields:
            if field.sort.is_enum() or field.sort.is_ptr():
                continue
            symbol = self.fragment_factory.field_symbol(field, step.parent.label, prefix=parent_prefix)
            fields[field.name] = symbol

        enum_fields: dict[str, str] = dict(step.parent.label.frame.enum_fields)

        parent_states = dict(zip(
            self.states_name,
            self._node_state_symbols(step.parent, prefix=parent_prefix)
        ))

        psi = self.sdta_ctx.psi(
            child_states,
            fields,
            enum_fields,
            parent_states
        )

        body = smt.And(
            psi,
            *conjuncts
        )
        head = self.apply(step.new_parent)
        clause = chc.Clause(body, head)
        return clause

    def _ptr_state_equalities(self, src_sainted_label: SaintedLabel, dest_sainted_label: SaintedLabel, updates: Iterable[tuple[str, int, int]], src_prefix: str = "", dest_prefix: str = "") -> Iterable[FNode]:
        for state_name in self.sdta_ctx.states:
            for (p, i, j) in updates:
                src_symbol = self._ptr_state_symbol_with_coordinates(src_sainted_label, state_name, (p, i), src_prefix)
                dest_symbol = self._ptr_state_symbol_with_coordinates(dest_sainted_label, state_name, (p, j), dest_prefix)
                yield smt.Equals(src_symbol, dest_symbol)

    def _start_of_state_propagation(self, step: StartStatePropagation) -> FNode:
        equalities: list[FNode] = []
        for coordinates in step.propagation_coordinates:
            for state_name in self.sdta_ctx.states:
                target_symbol = self._ptr_state_symbol_with_coordinates(step.sainted_label, state_name, coordinates)
                dest_symbol = self._ptr_state_symbol_with_coordinates(step.new_sainted_label, state_name, coordinates)
                equalities.append(smt.Equals(target_symbol, dest_symbol))
        body = smt.And(
            self.apply(step.sainted_label),
            *equalities
        )
        head = self.apply(step.new_sainted_label)
        clause = chc.Clause(body, head)
        return clause

    def _internal_state_propagation(self, step: InternalStatePropagation) -> FNode:
        equalities = self._ptr_state_equalities(step.sainted_sigma, step.new_sainted_sigma, step.prpagations)
        body = smt.And(
            self.apply(step.sainted_sigma),
            *equalities
        )
        head = self.apply(step.new_sainted_sigma)
        clause = chc.Clause(body, head)
        return clause

    def _up_state_propagation(self, step: UpStatePropagation) -> FNode:
        equalities = self._ptr_state_equalities(step.sainted_sigma1, step.new_sainted_sigma2, step.prpagations, src_prefix="c", dest_prefix="p")
        body = smt.And(
            self.apply(step.sainted_sigma1, var_prefix="c"),
            self.apply(step.sainted_sigma2, var_prefix="p"),
            *equalities
        )
        head = self.apply(step.new_sainted_sigma2, var_prefix="p")
        clause = chc.Clause(body, head)
        return clause

    def _down_state_propagation(self, step: DownStatePropagation) -> FNode:
        equalities = self._ptr_state_equalities(step.sainted_sigma2, step.new_sainted_sigma2, step.prpagations, src_prefix="p", dest_prefix="c")
        body = smt.And(
            self.apply(step.sainted_sigma1, var_prefix="p"),
            self.apply(step.sainted_sigma2, var_prefix="c"),
            *equalities
        )
        head = self.apply(step.new_sainted_sigma2, var_prefix="c")
        clause = chc.Clause(body, head)
        return clause

    def _acceptance(self, step: Acceptance) -> FNode:
        states_dict = dict(zip(self.sdta_ctx.states.keys(), self._node_state_symbols(step.sainted_label)))
        body = smt.And(
            self.apply(step.sainted_label),
            self.sdta_ctx.psiF(states_dict)
        )
        head = smt.FALSE()
        clause = chc.Clause(body, head)
        return clause

    def S(self, step: SaintingStep) -> FNode: # noqa: N802
        match step:
            case Initialization() as initialization:
                return self._initialization(initialization)
            case AutomataTransition() as automaton_transition:
                return self._automaton_transition(automaton_transition)
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
