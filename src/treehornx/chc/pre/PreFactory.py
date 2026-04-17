from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import product
from typing import Callable, Iterable, Literal

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smty
from pysmt.fnode import FNode

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.computation.LabFactory import LabFactory
from treehornx.chc.pre.PreContext import PreContext
from treehornx.chc.utils import label_exit
from treehornx.enum_labels.core.Dir import Down
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.expressions import Var
from treehornx.ir.sorts import BOOL, Int


class PreFactoryError(Exception):
    pass



@dataclass
class PreFactory:
    ctx: PreContext
    lab_factory: LabFactory


    def __post_init__(self):
        self.fragment_factory = self.lab_factory.fragment_factory

    def _id(self, lab: Label) -> str:
        return self.fragment_factory.id_getter(lab)

    def _state_symbol(self, label: Label, state: str, prefix: str = "") -> FNode:
        backbone_lab = label.origin_at(0)
        backbone_lab_id = self._id(backbone_lab)
        symbol_name = f"{prefix}q{backbone_lab_id}_{state}"
        symbol_type = smty.INT if self.ctx.states[state] == "int" else smty.BOOL
        return smt.Symbol(symbol_name, symbol_type)

    def _state_var(self, state_name: str) -> Var:
        var_name = state_name
        var_sort = Int() if self.ctx.states[state_name] == "int" else BOOL
        return Var(var_name, var_sort)

    def _states_symbols(self, label: Label, prefix: str = "") -> list[FNode]:
        return [self._state_symbol(label, state, prefix) for state in self.ctx.states]

    def _states_dict(self, label: Label, prefix: str = "") -> dict[str, FNode]:
        return {state: self._state_symbol(label, state, prefix) for state in self.ctx.states}

    def _e_symbol(self, label: Label, var_prefix: str = "") -> FNode:
        name = f"{var_prefix}e{self._id(label)}"
        return smt.Symbol(name, smty.BOOL)

    def _args_symbols(self, label: Label, prefix: str = "") -> Iterable[FNode]:
        yield from self.fragment_factory.label_symbols(label, prefix)
        yield from self._states_symbols(label, prefix)
        yield self._e_symbol(label, var_prefix=prefix)

    def _pre_name(self, label: Label) -> str:
        return f"Pre{self._id(label)}"

    def predicate(self, label: Label) -> FNode:
        args = self._args_symbols(label)
        name = self._pre_name(label)
        return chc.Predicate(name, [arg.get_type() for arg in args])

    def _apply(self, label: Label, var_prefix: str = "") -> FNode:
        args = list(self._args_symbols(label, prefix=var_prefix))
        predicate = self.predicate(label)
        app = chc.Apply(predicate, args)
        return app

    def pre_I(self, label: Label, exit_codes: set[ExitCodeKind]) -> FNode:  # noqa: N802
        if label[0].active:
            raise PreFactoryError(
                f"Label is active, but pre_I should only be called on labels inactive at the begin of the computation."
            )
        lab = self.lab_factory.apply(label)
        e = self._e_symbol(label)
        body = smt.And(lab, smt.Iff(e, label_exit(label, exit_codes))).simplify()
        head = self._apply(label)
        return chc.Clause(body, head)

    def pre_II(self, parent: Label, children: Iterable[tuple[str|int, Label]], exit_codes: set[ExitCodeKind]) -> FNode:  # noqa: N802

        children = list(children)
        assert set(tup[0] for tup in children) == set(child_key for child_key in parent.frame.active_child.keys()), \
        "Children keys do not match the label's children keys."

        data_constraints: list[FNode] = []
        pres: list[FNode] = []
        children_states: dict[str | int, dict[str, FNode] | None] = dict()
        es: list[FNode] = []
        parent_var_prefix = "p"
        for child_index, (child_key, child) in enumerate(children):
            child_var_prefix = f"c{child_index}"

            pre = self._apply(child, var_prefix=child_var_prefix)
            pres.append(pre)
            consistency_constraints = self.fragment_factory.cross_data_constraints(
                parent,
                child,
                child_key,
                parent_variable_prefix=parent_var_prefix,
                child_variable_prefix=child_var_prefix,
            )
            data_constraints.extend(consistency_constraints)
            if child[0].active:
                children_states[child_key] = self._states_dict(child, prefix=child_var_prefix)
            else:
                children_states[child_key] = None
            e = self._e_symbol(child, var_prefix=child_var_prefix)
            es.append(e)

        psi = None
        if parent[0].active:
            fields_names = tuple(
                var.name
                for var in self.fragment_factory.data_fields
                if not var.sort.is_enum() and not var.sort.is_ptr()
            )
            fields = dict(
                zip(
                    fields_names,
                    self.fragment_factory.last_frame_field_symbols(parent.origin_at(0), prefix=parent_var_prefix),
                )
            )
            states = self._states_dict(parent, prefix=parent_var_prefix)
            psi = self.ctx.psi(children_states, fields, states)

        e = self._e_symbol(parent, var_prefix=parent_var_prefix)
        lab = self.lab_factory.apply(parent, parent_var_prefix)
        if psi:
            body = smt.And(
                lab, *pres, *data_constraints, psi, smt.Iff(e, smt.Or(*es, label_exit(parent, exit_codes)))
            ).simplify()
        else:
            body = smt.And(
                lab, *pres, *data_constraints, smt.Iff(e, smt.Or(*es, label_exit(parent, exit_codes)))
            ).simplify()
        head = self._apply(parent, var_prefix=parent_var_prefix)
        return chc.Clause(body, head)

    def pre_III(self, label: Label, exit_codes: set[ExitCodeKind]) -> FNode:  # noqa: N802
        states = self._states_dict(label)
        psi_f = self.ctx.psiF(states)
        e = self._e_symbol(label)
        pre = self._apply(label)
        body = smt.And(pre, psi_f, e).simplify()
        head = smt.FALSE()
        return chc.Clause(body.simplify(), head)
