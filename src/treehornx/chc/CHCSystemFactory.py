from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, Literal

from pychc.chc_system import CHCSystem
from pysmt import logics

from treehornx.chc.factories.LabFactory import LabFactory
from treehornx.chc.factories.PreFactory import PreFactory
from treehornx.chc.factories.psi import *
from treehornx.chc.core import ExitCodeKind
from treehornx.enum_labels import KnittedTrees
from treehornx.enum_labels.core.Dir import Down, Internal, Up
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label
from treehornx.ir._internal.sorts.Struct import Struct
from treehornx.ir.function import Function

class PreKind(Enum):
    BST = 0
    BST_STRICT = 1
    SLL_SORTED = 2
    SLL_SORTED_STRICT = 3
    AVL = 4
    AVL_STRICT = 5

@dataclass
class CHCSystemFactory:
    function: Function
    tree_node_sort: Struct
    trees: KnittedTrees

    def _query_required(self, lab: Label, exit_code: ExitCodeKind) -> bool:
        match exit_code:
            case ExitCodeKind.ERR:
                return ERR() in lab.frame.events
            case ExitCodeKind.OOM:
                return OOM() in lab.frame.events
            case ExitCodeKind.LABEL_OVERFLOW:
                return LOF() in lab.frame.events
            case ExitCodeKind.CLEAN:
                return Exit()in lab.frame.events

    def _add_lab_predicates(self, system: CHCSystem, lab_factory: LabFactory):

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

    def _add_lab_queries(self, system: CHCSystem, lab_factory: LabFactory, exit_code: ExitCodeKind):
        for lab in self.trees.labels():
            if self._query_required(lab, exit_code):
                chc = lab_factory.query(lab)
                system.add_clause(chc)

    def _add_pre_predicates(self, system: CHCSystem, pre_factory: PreFactory, exit_code: ExitCodeKind):

        for lab in self.trees.labels():
            pred = pre_factory.predicate(lab)
            system.add_predicate(pred)

        for lab in self.trees.labels():
            if not lab[0].active and not self.trees.is_root_label(lab):
                chc = pre_factory.pre_I(lab, {exit_code})
                system.add_clause(chc)

            else:
                for chc in pre_factory.pre_II(lab, {exit_code}):
                    system.add_clause(chc)

        for lab in self.trees.labels():
            if self.trees.is_root_label(lab):
                chc = pre_factory.pre_III(lab, {exit_code})
                system.add_clause(chc)

    def _add_pre_queries(self, system: CHCSystem, pre_factory: PreFactory, exit_code: ExitCodeKind):
        for lab in self.trees.labels():
            if self.trees.is_root_label(lab):
                chc = pre_factory.pre_III(lab, {exit_code})
                system.add_clause(chc)

    def make_system(self, exit_code: ExitCodeKind) -> CHCSystem:
        factory = LabFactory(self.function, self.tree_node_sort, self.trees)
        system = CHCSystem(logic=logics.QF_UFLIA)

        self._add_lab_predicates(system, factory)
        self._add_lab_queries(system, factory, exit_code)
        return system

    def make_system_with_pre(self, exit_code: ExitCodeKind, pre_kind: PreKind) -> CHCSystem:
        lab_factory = LabFactory(self.function, self.tree_node_sort, self.trees)
        pre_factory = self._pre_factory(lab_factory, pre_kind)

        system = CHCSystem(logic=logics.QF_UFLIA)

        self._add_lab_predicates(system, lab_factory)
        self._add_pre_predicates(system, pre_factory, exit_code)
        self._add_pre_queries(system, pre_factory, exit_code)
        return system

    def _pre_factory(self, lab_factory: LabFactory, pre_kind: PreKind) -> PreFactory:
        match pre_kind:
            case PreKind.BST:
                psi, psiF = psi_bst, psiF_empty # noqa: N806
                q: dict[str, Literal['int', 'bool']] = {'min': 'int', 'max': 'int', 'data': 'int'}
            case PreKind.BST_STRICT:
                psi, psiF = psi_bst_strict, psiF_empty # noqa: N806
                q = {'min': 'int', 'max': 'int', 'data': 'int'}
            case PreKind.SLL_SORTED:
                psi, psiF = psi_sll_sorted, psiF_empty # noqa: N806
                q = {'data': 'int'}
            case PreKind.SLL_SORTED_STRICT:
                psi, psiF = psi_sll_sorted_strict, psiF_empty # noqa: N806
                q = {'data': 'int'}
            case PreKind.AVL:
                psi, psiF = psi_avl, psiF_empty # noqa: N806
                q = {'min': 'int', 'max': 'int', 'data': 'int', 'height': 'int'}
            case PreKind.AVL_STRICT:
                psi, psiF = psi_avl_strict, psiF_empty # noqa: N806
                q = {'min': 'int', 'max': 'int', 'data': 'int', 'height': 'int'}

        return PreFactory(q, lab_factory, psi, psiF)
