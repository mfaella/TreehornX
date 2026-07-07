from dataclasses import dataclass
from functools import cache, cached_property
from typing import Iterable

from frozendict import frozendict
from pychc.chc_system import CHCSystem
from pysmt import logics
from pysmt.fnode import FNode
import pysmt.shortcuts as smt

from treehornx.chc.computation import *
from treehornx.chc.contracts import constract_with_Pre_predicates, produce_contract_queries, produce_contract_with_Pre
from treehornx.chc.contracts.Contract import Contract
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.post import S_predicates, S_with_Pre_predicates, T_predicates, produce_S, produce_S_with_Pre, produce_T_no_query, produce_T_queries
from treehornx.chc.post.SFactory import SFactory
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.post.helpers import last_assignment_to_field
from treehornx.chc.post.sainting.core import Q, SaintedLabel
from treehornx.chc.post.tainting.core import TaintedLabel
from treehornx.chc.pre import PreFactory
from treehornx.chc.pre import pre_predicates, produce_pre_no_query, produce_pre_queries
from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.chc.utils.helpers import label_exit
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Down, Internal, Up
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label
from treehornx.ir._internal.sorts.Struct import Struct
from treehornx.ir.function import Function

from loguru import logger

from .computation import LabFactory

@dataclass
class CHCSystemFactory:
    function: Function
    tree_node_sort: Struct
    trees: KnittedTrees
    pre_ctx: SDTAContext | None = None
    post_ctx: SDTAContext | bool | None | Contract[TaintedLabel] = None
    root_name: str | None = None
    parent_name: str | None = None

    def __post_init__(self):
        if self.post_ctx and self.root_name is None:
            raise ValueError("Root name must be provided if postcondition generation is enabled.")


    @cached_property
    def fragment_factory(self):
        data_variables = tuple(var for var in self.function.vars if not var.sort.is_ptr() and not var.sort.is_enum())
        data_fields = tuple(
            field
            for field in self.tree_node_sort.fields.values()
            if not field.sort.is_ptr() and not field.sort.is_enum()
        )
        fragment_factory = CHCFragmentFactory(
            data_variables=data_variables, data_fields=data_fields, id_getter=lambda lab: str(self.trees.id(lab))
        )
        return fragment_factory

    @cached_property
    def lab_factory(self) -> LabFactory:
        return LabFactory(self.function, self.fragment_factory)

    def consistent_child_S(self, parent: SaintedLabel, child_key: str | int, child: SaintedLabel, p_var_prefix: str, c_var_prefix: str) -> FNode:
        return smt.And(
            self.consistent_child(parent.label, child_key, child.label, p_var_prefix, c_var_prefix),
            self.S_factory.consistent_child_S(parent, child_key, child, p_var_prefix, c_var_prefix)
        )

    @cached_property
    def contract_pre_factory(self) -> PreFactory[TaintedLabel]:
        if self.pre_ctx is None:
            raise ValueError("No context provided for precondition generation.")
        if not isinstance(self.post_ctx, Contract):
            raise ValueError("No contract provided for precondition generation.")


        def property(lab: TaintedLabel, prefix: str) -> FNode:
            return self.post_ctx.fail(lab, prefix) # pyright: ignore

        def consistent_children(parent: TaintedLabel, children: Iterable[tuple[str|int, TaintedLabel]]) -> FNode:
            children = list(children)
            consistency_constraints: list[FNode] = []
            for child_index, (child_key, child) in enumerate(children):
                child_var_prefix = f"c{child_index}"
                consistency_constraints.append(self.consistent_child_t(parent, child_key, child, "p", child_var_prefix))

            return smt.And(*consistency_constraints)

        return PreFactory[TaintedLabel](
            property=property,
            consistent_children=consistent_children,
            ctx=self.pre_ctx,
            fragment_factory=self.fragment_factory,
            apply_predicate=self.T_factory.apply,
            get_label=lambda tlab: tlab.label,
            get_name=lambda slab: str(self.trees.id(slab.label)),
            aux_symbols=lambda tlab, prefix: ()
        )


    @cached_property
    def post_pre_factory(self) -> PreFactory[SaintedLabel]:
        if self.pre_ctx is None:
            raise ValueError("No context provided for precondition generation.")
        if not self.post_ctx:
            raise ValueError("No post condition context provided")
        if self.post_ctx is True:
            raise ValueError("Postcondition generation is enabled, but no context provided for precondition generation.")

        def property(lab: SaintedLabel, _prefix: str) -> FNode:
            if lab.state_node != Q():
                return smt.FALSE()


            prop = self.S_factory.apply_psiF(lab, "p")

            logger.debug(prop)
            return prop

        def consistent_children(parent: SaintedLabel, children: Iterable[tuple[str|int, SaintedLabel]]) -> FNode:
            children = list(children)
            consistency_constraints: list[FNode] = []
            for child_index, (child_key, child) in enumerate(children):
                logger.debug(f"Adding consistency constraints for child ({child_key}, {self.S_factory.label_name(child)}) of parent {self.S_factory.label_name(parent)} with index {child_index}")
                child_var_prefix = f"c{child_index}"
                consistency_constraints.append(self.consistent_child_S(parent, child_key, child, "p", child_var_prefix))

            if parent.state_node == Q():
                transition_constraints = self.S_factory.automata_transition_constraints(parent, children)
                consistency_constraints.append(transition_constraints)

            return smt.And(*consistency_constraints)


        return PreFactory(
            property=property,
            consistent_children=consistent_children,
            ctx=self.pre_ctx,
            fragment_factory=self.fragment_factory,
            apply_predicate=self.S_factory.apply,
            get_label=lambda slab: slab.label,
            get_name=lambda slab: self.S_factory.label_name(slab),
            aux_symbols=self.S_factory.aux_symbols
        )

    @cached_property
    def T_factory(self) -> TFactory:  # noqa: N802
        return TFactory(self.lab_factory)

    @cached_property
    def S_factory(self) -> SFactory:  # noqa: N802
        if isinstance(self.post_ctx, (type(None), bool, Contract)):
            raise ValueError("No context provided for postcondition generation.")
        return SFactory(self.trees, self.post_ctx, self.T_factory)

    @cached_property
    def trivially_safe_for_err(self) -> bool:
        return not any(ERR() in lab.frame.events for lab in self.trees.labels())

    @cached_property
    def trivially_safe_for_oom(self) -> bool:
        return not any(OOM() in lab.frame.events for lab in self.trees.labels())

    @cached_property
    def trivially_safe_for_lof(self) -> bool:
        return not any(LOF() in lab.frame.events for lab in self.trees.labels())

    @cached_property
    def trivially_safe_for_post_is_tree(self) -> bool:
        if self.root_name is None:
            raise ValueError("Root name must be provided to determine if the program is trivially safe for postcondition generation.")
        return next(iter(produce_T_queries(self.trees, self.root_name, self.T_factory)), None) is None

    def _add_clause(self, system: CHCSystem, clause: FNode):
        logger.debug(f"adding clause: {clause}")
        system.add_clause(clause)

    def _query_required(self, lab: Label, exit_code: ExitCodeKind) -> bool:
        match exit_code:
            case ExitCodeKind.ERR:
                return ERR() in lab.frame.events
            case ExitCodeKind.OOM:
                return OOM() in lab.frame.events
            case ExitCodeKind.LABEL_OVERFLOW:
                return LOF() in lab.frame.events
            case ExitCodeKind.CLEAN:
                return Exit() in lab.frame.events

    def _add_lab(self, system: CHCSystem):
        lab_factory = self.lab_factory
        for lab in self.trees.labels():
            predicate = lab_factory.predicate(lab)
            system.add_predicate(predicate)

        for lab in self.trees.backbone_labels():
            chc = lab_factory.chc_I(lab)
            self._add_clause(system, chc)

        for lab in self.trees.start_labels():
            chc = lab_factory.chc_II(lab)
            self._add_clause(system, chc)

        for step in self.trees.steps():
            match step.dir:
                case Internal():
                    chc = lab_factory.chc_III(step)
                case Down(_):
                    chc = lab_factory.chc_IV(step)
                case Up():
                    chc = lab_factory.chc_V(step)
            self._add_clause(system, chc)

    def _add_lab_queries(self, system: CHCSystem, exit_code: ExitCodeKind):
        for lab in self.trees.labels():
            if self._query_required(lab, exit_code):
                chc = self.lab_factory.query(lab)
                self._add_clause(system, chc)

    def consistent_child(self, parent: Label, child_key: str | int, child: Label, p_var_prefix: str, c_var_prefix: str) -> FNode:
        return smt.And(*self.fragment_factory.cross_data_constraints(
            parent,
            child,
            child_key,
            parent_variable_prefix=p_var_prefix,
            child_variable_prefix=c_var_prefix,
        ))

    def consistent_child_t(self, parent: TaintedLabel, child_key: str | int, child: TaintedLabel, p_var_prefix: str, c_var_prefix: str) -> FNode:
        return self.consistent_child(parent.label, child_key, child.label, p_var_prefix, c_var_prefix)

    def consistent_chlidren(self, parent: Label, children: Iterable[tuple[str|int, Label]]) -> FNode:
        consistency_constraints: list[FNode] = []
        for child_index, (child_key, child) in enumerate(children):
            child_var_prefix = f"c{child_index}"
            consistency_constraints.append(self.consistent_child(parent, child_key, child, "p", child_var_prefix))

        return smt.And(*consistency_constraints)

    def pre_factory(self, exit_code: ExitCodeKind) -> PreFactory[Label]:
        if self.pre_ctx is None:
            raise ValueError("No context provided for precondition generation.")

        def get_label(lab: Label) -> Label:
            return lab

        pre_factory: PreFactory[Label] = PreFactory(
            property=lambda lab, _: label_exit(lab, {exit_code}),
            consistent_children=self.consistent_chlidren,
            ctx=self.pre_ctx,
            fragment_factory=self.fragment_factory,
            apply_predicate=self.lab_factory.apply,
            get_label=get_label,
            get_name=lambda lab: str(self.trees.id(lab)),
            aux_symbols=lambda lab, prefix: ()
        )
        return pre_factory

    def _add_pre(self, system: CHCSystem, exit_code: ExitCodeKind):
        pre_factory = self.pre_factory(exit_code)
        print(f"Adding preconditions for exit code: {exit_code.name}")
        for pred in pre_predicates(self.trees, pre_factory):
            system.add_predicate(pred)

        print(f"Added {len(list(pre_predicates(self.trees, pre_factory)))} precondition predicates.")
        print(f"Adding precondition clauses for exit code: {exit_code.name}")
        for chc in produce_pre_no_query(self.trees, pre_factory):
            self._add_clause(system, chc)

    def _add_pre_queries(self, system: CHCSystem, exit_code: ExitCodeKind):
        for chc in produce_pre_queries(self.trees, self.pre_factory(exit_code)):
            self._add_clause(system, chc)

    def _add_T(self, system: CHCSystem):  # noqa: N802
        T_factory = self.T_factory  # noqa: N806
        assert isinstance(self.root_name, str)

        for pred in T_predicates(self.trees, self.root_name, T_factory):
            system.add_predicate(pred)

        for chc in produce_T_no_query(self.trees, self.root_name, T_factory):
            self._add_clause(system, chc)

    def _add_T_queries(self, system: CHCSystem):  # noqa: N802
        T_factory = self.T_factory  # noqa: N806
        assert isinstance(self.root_name, str)
        for chc in produce_T_queries(self.trees, self.root_name, T_factory):
            self._add_clause(system, chc)

    def _add_S(self, system: CHCSystem): # noqa: N802
        S_factory = self.S_factory  # noqa: N806
        assert isinstance(self.root_name, str)

        if self.pre_ctx:
            logger.debug("adding S with Pre")
            pre_factory = self.post_pre_factory
            for pred in S_with_Pre_predicates(self.trees, self.root_name, S_factory, pre_factory):
                if pred not in system.get_predicates():
                    system.add_predicate(pred)
            logger.debug("predicates loaded")

            for chc in produce_S_with_Pre(self.trees, self.root_name, S_factory, pre_factory):
                self._add_clause(system, chc)
            logger.debug("clauses added")

        else:
            for pred in S_predicates(self.trees, self.root_name, S_factory):
                if pred not in system.get_predicates():
                    system.add_predicate(pred)

            for chc in produce_S(self.trees, self.root_name, S_factory):
                self._add_clause(system, chc)

    def _add_contract(self, system: CHCSystem):
        if not isinstance(self.post_ctx, Contract):
            raise ValueError("No contract provided for postcondition generation.")

        contract: Contract[TaintedLabel] = self.post_ctx

        if self.pre_ctx is None:
            for clause in produce_contract_queries(self.trees, contract, self.T_factory):
                self._add_clause(system, clause)

        else:
            pre_factory = self.contract_pre_factory
            for pred in constract_with_Pre_predicates(self.trees, pre_factory):
                if pred not in system.get_predicates():
                    system.add_predicate(pred)
            for clause in produce_contract_with_Pre(self.trees, pre_factory, self.parent_name):
                self._add_clause(system, clause)


    def make_system(self, exit_code: ExitCodeKind | None = None) -> CHCSystem:
        system = CHCSystem(logic=logics.QF_UFLIA)

        self._add_lab(system)

        print("creating system...")

        if not self.post_ctx:
            if self.pre_ctx is None and exit_code is not None:
                self._add_lab_queries(system, exit_code)
            elif exit_code is not None or self.pre_ctx is not None:
                print("Adding preconditions...")
                exit_code = exit_code or ExitCodeKind.CLEAN
                self._add_pre(system, exit_code)
                self._add_pre_queries(system, exit_code)

        else:
            print("Adding postconditions...")
            print("Adding T...")
            self._add_T(system)
            self._add_T_queries(system)

            match self.post_ctx:
                case SDTAContext():
                    print("Adding S...")
                    self._add_S(system)
                case Contract():
                    self._add_contract(system)
                case _:
                    pass

        return system
