from dataclasses import dataclass
from functools import cached_property

from pychc.chc_system import CHCSystem
from pysmt import logics

from treehornx.chc.computation import *
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.post import S_predicates, T_predicates, produce_S, produce_T_no_query, produce_T_queries
from treehornx.chc.post.SFactory import SFactory
from treehornx.chc.post.TFactory import TFactory
from treehornx.chc.pre import *
from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Down, Internal, Up
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label
from treehornx.ir._internal.sorts.Struct import Struct
from treehornx.ir.function import Function


@dataclass
class CHCSystemFactory:
    function: Function
    tree_node_sort: Struct
    trees: KnittedTrees
    pre_ctx: SDTAContext | None = None
    post_ctx: SDTAContext | bool | None = None
    root_name: str | None = None

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

    @cached_property
    def pre_factory(self) -> PreFactory:
        if self.pre_ctx is None:
            raise ValueError("No context provided for precondition generation.")
        return PreFactory(self.pre_ctx, self.lab_factory)

    @cached_property
    def T_factory(self) -> TFactory:  # noqa: N802
        return TFactory(self.lab_factory)

    @cached_property
    def S_factory(self) -> SFactory:  # noqa: N802
        if isinstance(self.post_ctx, (type(None), bool)):
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
            system.add_clause(chc)

        for lab in self.trees.start_labels():
            chc = lab_factory.chc_II(lab)
            system.add_clause(chc)

        for step in self.trees.steps():
            match step.dir:
                case Internal():
                    chc = lab_factory.chc_III(step)
                case Down(_):
                    chc = lab_factory.chc_IV(step)
                case Up():
                    chc = lab_factory.chc_V(step)
            system.add_clause(chc)

    def _add_lab_queries(self, system: CHCSystem, exit_code: ExitCodeKind):
        for lab in self.trees.labels():
            if self._query_required(lab, exit_code):
                chc = self.lab_factory.query(lab)
                system.add_clause(chc)

    def _add_pre(self, system: CHCSystem, exit_code: ExitCodeKind):
        pre_factory = self.pre_factory
        for pred in pre_predicates(self.trees, pre_factory):
            system.add_predicate(pred)

        for chc in produce_pre_no_query(self.trees, pre_factory, {exit_code}):
            system.add_clause(chc)

    def _add_pre_queries(self, system: CHCSystem, exit_code: ExitCodeKind):
        for chc in produce_pre_queries(self.trees, self.pre_factory, {exit_code}):
            system.add_clause(chc)

    def _add_T(self, system: CHCSystem):  # noqa: N802
        T_factory = self.T_factory  # noqa: N806
        assert isinstance(self.root_name, str)

        for pred in T_predicates(self.trees, self.root_name, T_factory):
            system.add_predicate(pred)

        for chc in produce_T_no_query(self.trees, self.root_name, T_factory):
            system.add_clause(chc)

    def _add_T_queries(self, system: CHCSystem):  # noqa: N802
        T_factory = self.T_factory  # noqa: N806
        assert isinstance(self.root_name, str)
        for chc in produce_T_queries(self.trees, self.root_name, T_factory):
            system.add_clause(chc)

    def _add_S(self, system: CHCSystem): # noqa: N802
        S_factory = self.S_factory  # noqa: N806
        assert isinstance(self.root_name, str)

        for pred in S_predicates(self.trees, self.root_name, S_factory):
            system.add_predicate(pred)

        for chc in produce_S(self.trees, self.root_name, S_factory):
            system.add_clause(chc)

    def make_system(self, exit_code: ExitCodeKind | None = None) -> CHCSystem:
        system = CHCSystem(logic=logics.QF_UFLIA)

        self._add_lab(system)

        if self.pre_ctx is None and exit_code is not None:
            self._add_lab_queries(system, exit_code)
        elif exit_code is not None or self.pre_ctx is not None:
            exit_code = exit_code or ExitCodeKind.CLEAN
            self._add_pre(system, exit_code)
            self._add_pre_queries(system, exit_code)

        if self.post_ctx:
            self._add_T(system)
            self._add_T_queries(system)

            if self.post_ctx is not True:
                self._add_S(system)

        return system
