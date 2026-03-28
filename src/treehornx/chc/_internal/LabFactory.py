from dataclasses import dataclass
from functools import cached_property
from typing import Callable, Iterable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx.enum_labels import LaceOverApproximation, Step
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
from treehornx.ir.sorts import INT, REAL, Sort, Struct


@dataclass
class LabFactory:
    function: Function
    tree_node_sort: Struct
    lace_over_approx: LaceOverApproximation

    @cached_property
    def ir_type_to_smt2_sort(self) -> dict[Sort, smtty.PySMTType]:
        return {INT: smtty.INT, REAL: smtty.REAL}

    def _data_variables(self) -> Iterable[Var]:
        return (v for v in self.function.vars if not (v.sort.is_enum() or v.sort.is_ptr()))

    def _data_fields(self) -> Iterable[Var]:
        return (v for v in self.tree_node_sort.fields.values() if not (v.sort.is_enum() or v.sort.is_ptr()))

    def _id(self, lab: Label) -> int:
        return self.lace_over_approx.id(lab)

    def _var_symbol(self, var: Var, lab: Label, prefix: str = "") -> FNode:
        symbol_name = f"{prefix}{self._id(lab)}_{var.name}"
        symbol_type = self.ir_type_to_smt2_sort[var.sort]
        return smt.Symbol(symbol_name, symbol_type)

    def _last_frame_bounded_vars(self, lab: Label) -> Iterable[FNode]:
        for var in self._data_variables():
            yield self._var_symbol(var, lab, prefix="v")
        for field in self._data_fields():
            yield self._var_symbol(field, lab, prefix="f")

    def _label_bounded_vars(self, lab: Label) -> Iterable[FNode]:
        for origin in lab.iter_origins():
            yield from self._last_frame_bounded_vars(origin)

    def predicate(self, lab: Label) -> FNode:
        bounded_variables = self._label_bounded_vars(lab)
        return chc.Predicate(f"Lab{self._id(lab)}", [var.get_type() for var in bounded_variables])

    def apply(self, lab: Label) -> FNode:
        bounded_variables = self._label_bounded_vars(lab)
        predicate = self.predicate(lab)
        return chc.Apply(predicate, list(bounded_variables))

    def fact(self, lab: Label) -> FNode:
        predicate_application = self.apply(lab)
        return predicate_application

    def chc_I(self, lab: Label) -> FNode:  # noqa: N802
        return self.fact(lab)

    def chc_II(self, lab: Label) -> FNode:  # noqa: N802
        return self.fact(lab)

    def _equality_constraints(
        self, inlab: Label, outlab: Label, exclude_symbols: set[FNode] = set()
    ) -> Iterable[FNode]:
        for left, right in zip(self._last_frame_bounded_vars(inlab), self._last_frame_bounded_vars(outlab)):
            if left not in exclude_symbols and right not in exclude_symbols:
                yield smt.Equals(left, right)

    def _expr_to_smt(self, expr: Expr, inlab: Label) -> FNode:
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
                return self._var_symbol(expr, inlab, prefix="v")
            case Field(_, name):
                var = self.tree_node_sort.fields[name]
                return self._var_symbol(var, inlab, prefix="f")
            case int():
                return smt.Int(expr)
            case float():
                return smt.Real(expr)
            case Not() | Eq() | Ne() | Lt() | Gt() | Le() | Ge() | Sub() | Div() | And() | Or() | Add() | Mul():
                args = (self._expr_to_smt(arg, inlab) for arg in expr.args())
                converter = op_converter_map[type(expr)]
                return converter(*args)
            case EnumConst() | PtrIsPtr() | PtrIsNil():
                raise RuntimeError(f"Normalized expressions should not contain {type(expr).__name__}")
            case Negate() | Mod():
                raise NotImplementedError("Mod operator not supported in SMT2 conversion")

    def _internal_data_constraints(self, inlab: Label, outlab: Label) -> Iterable[FNode]:
        stmt = self.function.instructions[inlab.frame.pc]
        constraints: list[FNode] = []

        match stmt:
            case IfGoto(cond, _):
                branch_case = outlab.frame.pc != inlab.frame.pc + 1
                cond = cond if branch_case is True else Not(cond)
                cond = normalized_expr(cond, inlab.frame)
                if cond not in {TRUE, FALSE}:
                    cond_smt = self._expr_to_smt(cond, inlab)
                    constraints.append(cond_smt)
                constraints.extend(self._equality_constraints(inlab, outlab))
            case VarAssignExpr(var, expr) if var.sort.is_enum():
                if outlab.frame.enum_fields[var.name] == "FALSE":
                    expr = Not(expr)
                expr = normalized_expr(expr, inlab.frame)
                if expr not in {TRUE, FALSE}:
                    expr_smt = self._expr_to_smt(expr, inlab)
                    constraints.append(expr_smt)
                constraints.extend(self._equality_constraints(inlab, outlab))
            case VarAssignExpr(var, expr):
                expr = normalized_expr(expr, inlab.frame)
                if isinstance(expr, Field):
                    field_var = self.tree_node_sort.fields[expr.name]
                    expr_smt = self._var_symbol(field_var, inlab, prefix="f")
                else:
                    expr_smt = self._expr_to_smt(expr, inlab)
                var_smt = self._var_symbol(var, outlab, prefix="v")
                constraints.append(smt.Equals(var_smt, expr_smt))
                constraints.extend(
                    constraint for constraint in self._equality_constraints(inlab, outlab, exclude_symbols={var_smt})
                )
            case FieldAssignExpr(field, expr) if sort_of(field).is_enum():
                if outlab.frame.enum_fields[field.name] == "FALSE":
                    expr = Not(expr)
                expr = normalized_expr(expr, inlab.frame)
                if expr not in {TRUE, FALSE}:
                    expr_smt = self._expr_to_smt(expr, inlab)
                    constraints.append(expr_smt)
                constraints.extend(self._equality_constraints(inlab, outlab))
            case FieldAssignExpr(field, expr):
                field_var = self.tree_node_sort.fields[field.name]
                field_smt = self._var_symbol(field_var, outlab, prefix="f")
                expr = normalized_expr(expr, inlab.frame)
                expr_smt = self._expr_to_smt(expr, inlab)
                constraints.append(smt.Equals(field_smt, expr_smt))
                constraints.extend(
                    constraint for constraint in self._equality_constraints(inlab, outlab, exclude_symbols={field_smt})
                )
            case _:
                constraints.extend(self._equality_constraints(inlab, outlab))
        return iter(constraints)

    def _step_chc(self, head_lab: Label, body_labs: Iterable[Label], data_constraints: Iterable[FNode]):
        body_predicates_application = tuple(self.apply(body_lab) for body_lab in body_labs)
        data_constraints = tuple(data_constraints)
        body = smt.And(*body_predicates_application, *data_constraints)
        head = self.apply(head_lab)
        formula = chc.Clause(body, head)
        return formula

    def chc_III(self, step: Step) -> FNode:  # noqa: N802
        data_constraints = self._internal_data_constraints(step.in_label, step.out_label)
        formula = self._step_chc(step.out_label, [step.in_label], data_constraints)
        return formula

    def _chc_external(self, step: Step) -> FNode:
        assert step.out_label.frame.prev is not None
        assert step.out_label.origin is not None
        data_constraints: list[FNode] = []
        dir = step.dir
        rev_dir = step.out_label.frame.prev[0]
        for outlab in step.in_label.iter_origins():
            if outlab.frame.prev and outlab.frame.prev[0] == dir:
                inlab = step.out_label.origin_at(outlab.frame.prev[1])
                data_constraints.extend(self._equality_constraints(inlab, outlab))
        for outlab in step.out_label.iter_origins():
            if outlab.frame.prev and outlab.frame.prev[0] == rev_dir:
                inlab = step.in_label.origin_at(outlab.frame.prev[1])
                data_constraints.extend(self._equality_constraints(inlab, outlab))
        formula = self._step_chc(step.out_label, [step.in_label, step.out_label.origin], data_constraints)
        return formula

    def chc_IV(self, step: Step) -> FNode:  # noqa: N802
        return self._chc_external(step)

    def chc_V(self, step: Step) -> FNode:  # noqa: N802
        return self._chc_external(step)

    def query(self, lab: Label) -> FNode:
        predicate_application = self.apply(lab)
        return chc.Clause(predicate_application, smt.FALSE())
