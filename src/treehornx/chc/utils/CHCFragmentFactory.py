from dataclasses import dataclass
from typing import Callable, Iterable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx.enum_labels.core.Dir import Down, Up
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.expressions import Var
from treehornx.ir.sorts import BOOL, INT, REAL, Sort


@dataclass
class CHCFragmentFactory:
    data_variables: tuple[Var, ...]
    data_fields: tuple[Var, ...]
    id_getter: Callable[[Label], str]

    def __post_init__(self):
        names = set(v.name for v in self.data_variables)
        if len(names) != len(self.data_variables):
            raise ValueError("Duplicate variable names in data_variables")
        names = set(f.name for f in self.data_fields)
        if len(names) != len(self.data_fields):
            raise ValueError("Duplicate variable names in data_fields")

    def ir_type_to_smt2_sort(self, sort: Sort) -> smtty.PySMTType:
        if sort == BOOL:
            return smtty.BOOL
        elif sort == INT:
            return smtty.INT
        elif sort == REAL:
            return smtty.REAL
        else:
            raise NotImplementedError(f"Unsupported sort for SMT2 conversion: {sort}")

    def _id(self, lab: Label) -> str:
        return self.id_getter(lab)

    def symbol(self, var: Var, lab: Label, prefix: str = "") -> FNode:
        symbol_name = f"{prefix}{self._id(lab)}_{var.name}"
        symbol_type = self.ir_type_to_smt2_sort(var.sort)
        return smt.Symbol(symbol_name, symbol_type)

    def var_symbol(self, var: Var, lab: Label, prefix: str = "") -> FNode:
        return self.symbol(var, lab, f"{prefix}v")

    def field_symbol(self, field: Var, lab: Label, prefix: str = "") -> FNode:
        return self.symbol(field, lab, f"{prefix}f")

    def last_frame_field_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        for field in self.data_fields:
            yield self.field_symbol(field, lab, prefix)

    def last_frame_var_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        for var in self.data_variables:
            yield self.var_symbol(var, lab, prefix)

    def last_frame_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        yield from self.last_frame_var_symbols(lab, prefix)
        yield from self.last_frame_field_symbols(lab, prefix)

    def label_vars_symbols(self, lab: Label) -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self.last_frame_var_symbols(origin)

    def label_field_symbols(self, lab: Label) -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self.last_frame_field_symbols(origin)

    def label_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self.last_frame_symbols(origin, prefix)

    def predicate(self, name: str, lab: Label) -> FNode:
        symbols = list(self.label_symbols(lab))
        symbols_types = [symbol.get_type() for symbol in symbols]
        return chc.Predicate(f"{name}{self._id(lab)}", symbols_types)

    def apply(self, name: str, lab: Label, variables_prefix: str = "") -> FNode:
        symbols = list(self.label_symbols(lab, prefix=variables_prefix))
        predicate = self.predicate(name, lab)
        return chc.Apply(predicate, symbols)

    def cross_data_constraints(
        self,
        parent: Label,
        child: Label,
        child_key: str | int,
        parent_variable_prefix: str = "",
        child_variable_prefix: str = "",
    ) -> Iterable[FNode]:
        if parent.frame.prev is None or child.frame.prev is None:
            return iter(())
        for outlab in parent.iter_origins():
            if outlab.frame.prev and outlab.frame.prev[0] == Down(child_key):
                inlab = child.origin_at(outlab.frame.prev[1])
                for left, right in zip(
                    self.last_frame_var_symbols(inlab, prefix=child_variable_prefix),
                    self.last_frame_var_symbols(outlab, prefix=parent_variable_prefix),
                ):
                    yield smt.Equals(left, right)
        for outlab in child.iter_origins():
            if outlab.frame.prev and outlab.frame.prev[0] == Up():
                inlab = parent.origin_at(outlab.frame.prev[1])
                for left, right in zip(
                    self.last_frame_var_symbols(inlab, prefix=parent_variable_prefix),
                    self.last_frame_var_symbols(outlab, prefix=child_variable_prefix),
                ):
                    yield smt.Equals(left, right)
