

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable, Literal

from pysmt.fnode import FNode
import pysmt.shortcuts as smt
import pysmt.typing as smty
import pychc.shortcuts as chc

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.factories.LabFactory import LabFactory
from treehornx.chc.helpers import label_exit
from treehornx.enum_labels.core.Dir import Down
from treehornx.enum_labels.core.Label import Label

class PreFactoryError(Exception):
    pass

# children states, fields, states
type PsiType = Callable[[dict[str|int, dict[str, FNode]|None], dict[str, FNode], dict[str, FNode]], FNode]
type PsiFType = Callable[[dict[str, FNode]], FNode]

@dataclass
class PreFactory:
    q: dict[str, Literal['int', 'bool']]
    lab_factory: LabFactory
    psi: PsiType
    psiF: PsiFType # noqa: N815

    def __post_init__(self):
        self.trees = self.lab_factory.trees

    def _id(self, label: Label) -> int:
        return self.trees.id(label)

    def _state_symbol(self, label: Label, state: str, prefix: str = "") -> FNode:
        symbol_name = f"{prefix}q{self._id(label.origin_at(0))}_{state}"
        symbol_type = smty.INT if self.q[state] == 'int' else smty.BOOL
        return smt.Symbol(symbol_name, symbol_type)

    def _states_symbols(self, label: Label, prefix:str = "") -> list[FNode]:
        return [self._state_symbol(label, state, prefix) for state in self.q]

    def _states_dict(self, label: Label, prefix: str = "") -> dict[str, FNode]:
        return {state: self._state_symbol(label, state, prefix) for state in self.q}

    def _e(self, label: Label, var_prefix:str ="") -> FNode:
        return smt.Symbol(f"{var_prefix}e{self._id(label)}", smty.BOOL)

    def predicate(self, label: Label) -> FNode:
        pred_name = f"Pre{self._id(label)}"
        pred_args = list(self.lab_factory.label_bounded_symbols(label))
        pred_args.extend(self._state_symbol(label, state) for state in self.q)
        args_types = [*(arg.get_type() for arg in pred_args), smty.BOOL]
        return chc.Predicate(pred_name, args_types)

    def apply(self, label: Label, var_prefix:str ="") -> FNode:
        pred = self.predicate(label)
        vars = list(self.lab_factory.label_bounded_symbols(label, var_prefix))
        states = self._states_symbols(label, var_prefix)
        e = self._e(label, var_prefix)
        return chc.Apply(pred, [*vars, *states, e])

    def pre_I(self, label: Label, exit_codes: set[ExitCodeKind]) -> FNode: # noqa: N802
        if label[0].active:
            raise PreFactoryError(f"Label is active, but pre_I should only be called on labels inactive at the begin of the computation.")

        if self.trees.is_root_label(label):
            raise PreFactoryError(f"Label is a start label, but pre_I should only be called on auxiliary node labels.")

        lab = self.lab_factory.apply(label)
        e = self._e(label)
        body = smt.And(
            lab,
            smt.Iff(e, label_exit(label, exit_codes))
        ).simplify()
        head = self.apply(label)
        return chc.Clause(body, head)

    def pre_II(self, label: Label, exit_codes: set[ExitCodeKind]) -> Iterable[FNode]: # noqa: N802
        pairs_pow_set = [list(self.trees.pairs_by_parent_and_child_key(label, key)) for key in self.trees.child_keys]
        for pairs in product(*pairs_pow_set):
            data_constraints: list[FNode] = []
            pres: list[FNode] = []
            children_states: dict[str|int, dict[str, FNode]|None] = dict()
            es: list[FNode] = []
            parent_var_prefix = "p"
            for child_index, (parent, child, child_key) in enumerate(pairs):
                child_var_prefix = f"c{child_index}"

                pre = self.apply(child, var_prefix=child_var_prefix)
                pres.append(pre)
                consistency_constraints = self.lab_factory.cross_data_constraints(parent, child, child_key, parent_variable_prefix=parent_var_prefix, child_variable_prefix=child_var_prefix)
                data_constraints.extend(consistency_constraints)
                if child[0].active:
                    children_states[child_key] = self._states_dict(child, prefix=child_var_prefix)
                else:
                    children_states[child_key] = None
                e = self._e(child, var_prefix=child_var_prefix)
                es.append(e)

            psi = None
            if label[0].active:
                fields_names = tuple(
                    var.name
                    for var in self.lab_factory.tree_node_sort.fields.values()
                    if not var.sort.is_enum() and not var.sort.is_ptr()
                )
                fields = dict(zip(
                    fields_names,
                    self.lab_factory.last_frame_field_symbols(label.origin_at(0), prefix=parent_var_prefix)
                ))
                states = self._states_dict(label, prefix=parent_var_prefix)
                psi = self.psi(children_states, fields, states)

            e = self._e(label, var_prefix=parent_var_prefix)
            lab = self.lab_factory.apply(label, parent_var_prefix)
            if psi:
                body = smt.And(
                    lab,
                    *pres,
                    *data_constraints,
                    psi,
                    smt.Iff(
                        e,
                        smt.Or(
                            *es,
                            label_exit(label, exit_codes)
                        )
                    )
                ).simplify()
            else:
                body = smt.And(
                    lab,
                    *pres,
                    *data_constraints,
                    smt.Iff(
                        e,
                        smt.Or(
                            *es,
                            label_exit(label, exit_codes)
                        )
                    )
                ).simplify()
            head = self.apply(label, var_prefix=parent_var_prefix)
            yield chc.Clause(body, head)

    def pre_III(self, label: Label, exit_codes: set[ExitCodeKind]) -> FNode: # noqa: N802
        if not self.trees.is_root_label(label):
            raise PreFactoryError(f"Label is not a start label, but pre_III should only be called on start labels.")

        states = self._states_dict(label)
        psi_f = self.psiF(states)
        e = self._e(label)
        pre = self.apply(label)
        body = smt.And(
            pre,
            psi_f,
            e
        ).simplify()
        head = smt.FALSE()
        return chc.Clause(body.simplify(), head.simplify())
