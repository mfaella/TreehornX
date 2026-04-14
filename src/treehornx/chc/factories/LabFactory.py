from dataclasses import dataclass
from functools import cached_property
from typing import Callable, Iterable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx.enum_labels import KnittedTrees, Step
from treehornx.enum_labels.core.Dir import Dir, Down, Up
from treehornx.enum_labels.core.Label import Label
from treehornx.enum_labels.utils import normalized_expr
from treehornx.ir.expressions import (
    FALSE,
    TRUE,
    Add,
    And,
    Div,
    EnumConst,
    Eq,
    Expr,
    Field,
    Ge,
    Gt,
    Le,
    Lt,
    Mod,
    Mul,
    Ne,
    Negate,
    Not,
    Or,
    PtrIsNil,
    PtrIsPtr,
    Sub,
    Var,
    sort_of,
)
from treehornx.ir.function import Function
from treehornx.ir.instructions import FieldAssignExpr, IfGoto, VarAssignExpr
from treehornx.ir.sorts import BOOL, INT, REAL, Sort, Struct


@dataclass
class LabFactory:
    function: Function
    tree_node_sort: Struct
    trees: KnittedTrees

    @cached_property
    def ir_type_to_smt2_sort(self) -> dict[Sort, smtty.PySMTType]:
        return {INT: smtty.INT, REAL: smtty.REAL}

    def _data_variables(self) -> Iterable[Var]:
        return (v for v in self.function.vars if not (v.sort.is_enum() or v.sort.is_ptr()))

    def _data_fields(self) -> Iterable[Var]:
        return (v for v in self.tree_node_sort.fields.values() if not (v.sort.is_enum() or v.sort.is_ptr()))

    def _id(self, lab: Label) -> int:
        return self.trees.id(lab)

    def _symbol(self, var: Var, lab: Label, prefix: str = "") -> FNode:
        symbol_name = f"{prefix}{self._id(lab)}_{var.name}"
        symbol_type = self.ir_type_to_smt2_sort[var.sort]
        return smt.Symbol(symbol_name, symbol_type)

    def _var_symbol(self, var: Var, lab: Label, prefix: str = "") -> FNode:
        return self._symbol(var, lab, f"{prefix}v")

    def _field_symbol(self, field: Var, lab: Label, prefix: str = "") -> FNode:
        return self._symbol(field, lab, f"{prefix}f")

    def last_frame_field_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        for field in self._data_fields():
            yield self._field_symbol(field, lab, prefix)

    def last_frame_var_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        for var in self._data_variables():
            yield self._var_symbol(var, lab, prefix)

    def last_frame_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        yield from self.last_frame_var_symbols(lab, prefix)
        yield from self.last_frame_field_symbols(lab, prefix)

    def label_vars_symbols(self, lab: Label) -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self.last_frame_var_symbols(origin)

    def label_field_symbols(self, lab: Label) -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self.last_frame_field_symbols(origin)

    def label_bounded_symbols(self, lab: Label, prefix: str = "") -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self.last_frame_symbols(origin, prefix)

    def predicate(self, lab: Label) -> FNode:
        bounded_variables = self.label_bounded_symbols(lab)
        return chc.Predicate(f"Lab{self._id(lab)}", [var.get_type() for var in bounded_variables])

    def apply(self, lab: Label, variables_prefix: str = "") -> FNode:
        bounded_variables = self.label_bounded_symbols(lab, variables_prefix)
        predicate = self.predicate(lab)
        return chc.Apply(predicate, list(bounded_variables))

    def fact(self, lab: Label) -> FNode:
        predicate_application = self.apply(lab)
        return predicate_application

    def chc_I(self, lab: Label) -> FNode:  # noqa: N802
        return self.fact(lab)

    def chc_II(self, lab: Label) -> FNode:  # noqa: N802
        if len(lab) != 2:
            raise ValueError("chc_II should only be called on start labels, which should have exactly 2 components.")
        if not self.trees.is_start_label(lab):
            raise ValueError("chc_II should only be called on start labels.")
        constraints = list(self._internal_equality_constraints(lab.origin_at(0), lab))
        body = smt.And(*constraints)
        head = self.apply(lab)
        formula = chc.Clause(body, head)
        return formula

    def _internal_equality_constraints(
        self, inlab: Label, outlab: Label, exclude_symbols: set[FNode] = set()
    ) -> Iterable[FNode]:
        for left, right in zip(self.last_frame_symbols(inlab), self.last_frame_symbols(outlab)):
            if left not in exclude_symbols and right not in exclude_symbols:
                yield smt.Equals(left, right)

    def _expr_to_smt(self, expr: Expr, inlab: Label) -> FNode:
        expr = normalized_expr(expr, inlab.frame)
        op_converter_map: dict[type, Callable[..., FNode]] = {
            # unaries
            Not: smt.Not,
            # binaries
            Eq: smt.Equals,
            Ne: smt.NotEquals,
            Gt: smt.GT,
            Lt: smt.LT,
            Ge: smt.GE,
            Le: smt.LE,
            Sub: smt.Minus,
            Div: smt.Div,
            # variadics
            And: smt.And,
            Or: smt.Or,
            Add: smt.Plus,
            Mul: smt.Times,
        }
        match expr:
            case Var(name, _):
                return self._symbol(expr, inlab, prefix="v")
            case Field(_, name):
                var = self.tree_node_sort.fields[name]
                return self._symbol(var, inlab, prefix="f")
            case int():
                return smt.Int(expr)
            case float():
                return smt.Real(expr)
            case Ne(left, right) | Eq(left, right) if sort_of(left).is_enum():
                left = normalized_expr(left, inlab.frame)
                right = normalized_expr(right, inlab.frame)
                return smt.Bool(left == right)
            case Not() | Eq() | Ne() | Lt() | Gt() | Le() | Ge() | Sub() | Div() | And() | Or() | Add() | Mul():
                args = (self._expr_to_smt(arg, inlab) for arg in expr.args())
                converter = op_converter_map[type(expr)]
                return converter(*args)
            case EnumConst() | PtrIsPtr() | PtrIsNil():
                raise RuntimeError(f"Normalized expressions should not contain {type(expr).__name__}")
            case Negate() | Mod():
                raise NotImplementedError("Mod operator not supported in SMT2 conversion")

    def _internal_data_constraints(self, inlab: Label, outlab: Label) -> Iterable[FNode]:
        constraints: list[FNode] = []
        if inlab.frame.pc >= len(self.function.instructions):
            constraints.extend(self._internal_equality_constraints(inlab, outlab))
            return constraints

        stmt = self.function.instructions[inlab.frame.pc]

        match stmt:
            case IfGoto(cond, _):
                branch_case = outlab.frame.pc != inlab.frame.pc + 1
                cond = cond if branch_case is True else Not(cond)
                cond = normalized_expr(cond, inlab.frame)
                if cond not in {TRUE, FALSE}:
                    cond_smt = self._expr_to_smt(cond, inlab)
                    constraints.append(cond_smt)
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
            case VarAssignExpr(var, expr) if var.sort == BOOL:
                if outlab.frame.enum_vars[var.name] == "FALSE":
                    expr = Not(expr)
                expr = normalized_expr(expr, inlab.frame)
                if expr not in {TRUE, FALSE}:
                    expr_smt = self._expr_to_smt(expr, inlab)
                    constraints.append(expr_smt)
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
            case VarAssignExpr(var, expr) if var.sort.is_enum():
                pass
            case VarAssignExpr(var, expr):
                expr = normalized_expr(expr, inlab.frame)
                if isinstance(expr, Field):
                    field_var = self.tree_node_sort.fields[expr.name]
                    expr_smt = self._symbol(field_var, inlab, prefix="f")
                else:
                    expr_smt = self._expr_to_smt(expr, inlab)
                var_smt = self._symbol(var, outlab, prefix="v")
                constraints.append(smt.Equals(var_smt, expr_smt))
                constraints.extend(
                    constraint for constraint in self._internal_equality_constraints(inlab, outlab, exclude_symbols={var_smt})
                )
            case FieldAssignExpr(field, expr) if sort_of(field) == BOOL:
                if outlab.frame.enum_fields[field.name] == "FALSE":
                    expr = Not(expr)
                expr = normalized_expr(expr, inlab.frame)
                if expr not in {TRUE, FALSE}:
                    expr_smt = self._expr_to_smt(expr, inlab)
                    constraints.append(expr_smt)
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
            case FieldAssignExpr(field, expr) if sort_of(field).is_enum():
                pass
            case FieldAssignExpr(field, expr):
                field_var = self.tree_node_sort.fields[field.name]
                field_smt = self._symbol(field_var, outlab, prefix="f")
                expr = normalized_expr(expr, inlab.frame)
                expr_smt = self._expr_to_smt(expr, inlab)
                constraints.append(smt.Equals(field_smt, expr_smt))
                constraints.extend(
                    constraint for constraint in self._internal_equality_constraints(inlab, outlab, exclude_symbols={field_smt})
                )
            case _:
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
        return iter(constraints)

    def chc_III(self, step: Step) -> FNode:  # noqa: N802
        data_constraints = self._internal_data_constraints(step.in_label, step.out_label)
        body = smt.And(*data_constraints, self.apply(step.in_label))
        head = self.apply(step.out_label)
        formula = chc.Clause(body, head)
        return formula

    def cross_data_constraints(self, parent: Label, child: Label, child_key: str|int, parent_variable_prefix: str = "", child_variable_prefix: str = "") -> Iterable[FNode]:
        if parent.frame.prev is None or child.frame.prev is None:
            return iter(())
        for outlab in parent.iter_origins():
            if outlab.frame.prev and outlab.frame.prev[0] == Down(child_key):
                inlab = child.origin_at(outlab.frame.prev[1])
                for left, right in zip(self.last_frame_var_symbols(inlab, prefix=child_variable_prefix), self.last_frame_var_symbols(outlab, prefix=parent_variable_prefix)):
                    yield smt.Equals(left, right)
        for outlab in child.iter_origins():
            if outlab.frame.prev and outlab.frame.prev[0] == Up():
                inlab = parent.origin_at(outlab.frame.prev[1])
                for left, right in zip(self.last_frame_var_symbols(inlab, prefix=parent_variable_prefix), self.last_frame_var_symbols(outlab, prefix=child_variable_prefix)):
                    yield smt.Equals(left, right)

    def _chc_external(self, step: Step) -> FNode:
        assert step.out_label.frame.prev is not None
        assert step.out_label.origin is not None
        if isinstance(step.dir, Up):
            assert isinstance(step.out_label.frame.prev[0], Down)
            child_key = step.out_label.frame.prev[0].child
            parent = step.out_label
            child = step.in_label
            outlab_prefix = "p"
            inlab_prefix = "c"
        elif isinstance(step.dir, Down):
            child_key =  step.dir.child
            parent = step.in_label
            child = step.out_label
            outlab_prefix = "c"
            inlab_prefix = "p"
        else:
            raise ValueError(f"Invalid direction for external step: {step.dir}")
        data_constraints = list(self.cross_data_constraints(parent, child, child_key, parent_variable_prefix="p", child_variable_prefix="c"))

        for field in self._data_fields():
            left = self._field_symbol(field, step.out_label.origin, prefix=outlab_prefix)
            right = self._field_symbol(field, step.out_label, prefix=outlab_prefix)
            data_constraints.append(smt.Equals(left, right))
        inlab_app = self.apply(step.in_label, variables_prefix=inlab_prefix)
        outlab_origin_app = self.apply(step.out_label.origin, variables_prefix=outlab_prefix)
        body = smt.And(*data_constraints, inlab_app, outlab_origin_app)
        head = self.apply(step.out_label, variables_prefix=outlab_prefix)
        formula = chc.Clause(
            body,
            head
        )
        return formula

    def chc_IV(self, step: Step) -> FNode:  # noqa: N802
        return self._chc_external(step)

    def chc_V(self, step: Step) -> FNode:  # noqa: N802
        return self._chc_external(step)

    def query(self, lab: Label) -> FNode:
        predicate_application = self.apply(lab)
        return chc.Clause(predicate_application, smt.FALSE())
