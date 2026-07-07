from dataclasses import dataclass
from functools import cached_property
from time import strftime
from typing import TYPE_CHECKING, Callable, Iterable

from frozendict import frozendict
from loguru import logger
import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smty
from pysmt.fnode import FNode

from treehornx.chc.computation.LabFactory import LabFactory
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.utils import label_exit
from treehornx.chc.utils.CHCFragmentFactory import CHCFragmentFactory
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.expressions import Var
from treehornx.ir.sorts import BOOL, Int


class PreFactoryError(Exception):
    pass


@dataclass
class PreFactory[T]:
    property: Callable[[T, str], FNode]
    consistent_children: Callable[[T, Iterable[tuple[str|int, T]]], FNode]
    ctx: SDTAContext
    fragment_factory: CHCFragmentFactory
    aux_symbols: Callable[[T, str], Iterable[FNode]]
    apply_predicate: Callable[[T, str], FNode]
    get_label: Callable[[T], Label]
    get_name: Callable[[T], str]

    def _state_symbol(self, label: T, state: str, prefix: str = "") -> FNode:
        lab_id = self.get_name(label)
        symbol_name = f"{prefix}q{lab_id}_{state}"
        symbol_type = smty.INT if self.ctx.states[state] == "int" else smty.BOOL
        return smt.Symbol(symbol_name, symbol_type)

    def _state_var(self, state_name: str) -> Var:
        var_name = state_name
        var_sort = Int() if self.ctx.states[state_name] == "int" else BOOL
        return Var(var_name, var_sort)

    def _states_symbols(self, label: T, prefix: str = "") -> list[FNode]:
        return [self._state_symbol(label, state, prefix) for state in self.ctx.states]

    def _states_dict(self, label: T, prefix: str = "") -> dict[str, FNode]:
        return {state: self._state_symbol(label, state, prefix) for state in self.ctx.states}

    def _e_symbol(self, label: T, var_prefix: str = "") -> FNode:
        name = f"{var_prefix}e{self.get_name(label)}"
        return smt.Symbol(name, smty.BOOL)

    def _args_symbols(self, label: T, prefix: str = "") -> Iterable[FNode]:
        yield from self.fragment_factory.label_symbols(self.get_label(label), prefix)
        yield from self._states_symbols(label, prefix)
        yield self._e_symbol(label, var_prefix=prefix)

    def _pre_name(self, label: T) -> str:
        return f"Pre{self.get_name(label)}"

    def predicate(self, label: T) -> FNode:
        args = [*self._args_symbols(label), *self.aux_symbols(label, "")]
        name = self._pre_name(label)
        return chc.Predicate(name, [arg.get_type() for arg in args])

    def _apply(self, label: T, var_prefix: str = "") -> FNode:
        args = [*self._args_symbols(label, prefix=var_prefix), *self.aux_symbols(label, var_prefix)]
        predicate = self.predicate(label)
        app = chc.Apply(predicate, args)
        return app

    def pre_I(self, decorated_label: T) -> FNode:  # noqa: N802
        label = self.get_label(decorated_label)
        if label[0].active:
            raise PreFactoryError(
                f"Label is active, but pre_I should only be called on labels inactive at the begin of the computation."
            )
        lab = self.apply_predicate(decorated_label, "")
        e = self._e_symbol(decorated_label)
        property = self.property(decorated_label, "")
        body = smt.And(lab, smt.Iff(e, property)).simplify()
        head = self._apply(decorated_label)
        clause = chc.Clause(body, head)
        return clause

    def pre_II( # noqa: N802
        self, decorated_parent: T, children: Iterable[tuple[str | int, T]]
    ) -> FNode:
        logger.debug(f"pre II for parent: {self.get_name(decorated_parent)} with children: {[self.get_name(child) for _, child in children]}")
        parent = self.get_label(decorated_parent)
        children = list(child for child in children if isinstance(child[0], str))

        data_constraints: list[FNode] = []
        pres: list[FNode] = []
        children_states: dict[str, dict[str, FNode] | None] = dict()
        es: list[FNode] = []
        parent_var_prefix = "p"
        consistency_constraints = self.consistent_children(decorated_parent, children)
        logger.debug(f"Consistency constraints for: {consistency_constraints}")
        data_constraints.append(consistency_constraints)
        for child_index, (child_key, decorated_child) in enumerate(children):
            logger.debug(f"Gathering contraints of {self.get_name(decorated_child)} as '{child_key}' child and {child_index} index")
            if isinstance(child_key, int):
                continue


            child_var_prefix = f"c{child_index}"
            child = self.get_label(decorated_child)
            pre = self._apply(decorated_child, var_prefix=child_var_prefix)
            pres.append(pre)
            if child[0].active:
                children_states[child_key] = self._states_dict(decorated_child, prefix=child_var_prefix)
            else:
                children_states[child_key] = None
            e = self._e_symbol(decorated_child, var_prefix=child_var_prefix)
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
            states = self._states_dict(decorated_parent, prefix=parent_var_prefix)
            enum_fields = dict(parent[0].enum_fields)
            psi = self.ctx.psi(children_states, fields, enum_fields, states)

        e = self._e_symbol(decorated_parent, var_prefix=parent_var_prefix)
        lab = self.apply_predicate(decorated_parent, parent_var_prefix)
        property = self.property(decorated_parent, parent_var_prefix)
        if psi:
            body = smt.And(
                lab, *pres, *data_constraints, psi, smt.Iff(e, smt.Or(*es, property))
            ).simplify()
        else:
            body = smt.And(
                lab, *pres, *data_constraints, smt.Iff(e, smt.Or(*es, property))
            ).simplify()
        head = self._apply(decorated_parent, var_prefix=parent_var_prefix)
        return chc.Clause(body, head)

    def pre_III(self, decorated_label: T) -> FNode:  # noqa: N802
        states = self._states_dict(decorated_label)
        psi_f = self.ctx.psiF(states)
        e = self._e_symbol(decorated_label)
        pre = self._apply(decorated_label)
        body = smt.And(pre, psi_f, e).simplify()
        head = smt.FALSE()
        return chc.Clause(body.simplify(), head)
