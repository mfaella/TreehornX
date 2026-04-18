from dataclasses import dataclass
from functools import cached_property
from typing import Callable, Iterable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx.chc.utils import CHCFragmentFactory
from treehornx.enum_labels import Step
from treehornx.enum_labels.core.Dir import Down, Up
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
    fragment_factory: CHCFragmentFactory

    def _data_field(self, name: str) -> Var:
        return next(field for field in self.fragment_factory.data_fields if field.name == name)

    def _data_variable(self, name: str) -> Var:
        return next(var for var in self.fragment_factory.data_variables if var.name == name)

    def predicate(self, lab: Label) -> FNode:
        return self.fragment_factory.predicate("Lab", lab)

    def apply(self, lab: Label, variables_prefix: str = "") -> FNode:
        return self.fragment_factory.apply("Lab", lab, variables_prefix=variables_prefix)

    def fact(self, lab: Label) -> FNode:
        predicate_application = self.apply(lab)
        return predicate_application

    def chc_I(self, lab: Label) -> FNode:  # noqa: N802
        return self.fact(lab)

    def chc_II(self, lab: Label) -> FNode:  # noqa: N802
        constraints = list(self._internal_equality_constraints(lab.origin_at(0), lab.origin_at(1)))
        body = smt.And(*constraints)
        head = self.apply(lab)
        formula = chc.Clause(body, head)
        return formula

    def _internal_equality_constraints(
        self, inlab: Label, outlab: Label, exclude_symbols: set[FNode] = set()
    ) -> Iterable[FNode]:
        for left, right in zip(
            self.fragment_factory.last_frame_symbols(inlab),
            self.fragment_factory.last_frame_symbols(outlab)
        ):
            if left not in exclude_symbols and right not in exclude_symbols:
                yield smt.Equals(left, right)

    def _expr_to_smt(self, expr: Expr, inlab: Label) -> FNode:
        expr = normalized_expr(expr, inlab)
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
                return self.fragment_factory.var_symbol(expr, inlab)
            case Field(_, name):
                field = self._data_field(expr.name)
                return self.fragment_factory.field_symbol(field, inlab)
            case int():
                return smt.Int(expr)
            case float():
                return smt.Real(expr)
            case Ne(left, right) | Eq(left, right) if sort_of(left).is_enum():
                left = normalized_expr(left, inlab)
                right = normalized_expr(right, inlab)
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
                cond = normalized_expr(cond, inlab)
                if cond not in {TRUE, FALSE}:
                    cond_smt = self._expr_to_smt(cond, inlab)
                    constraints.append(cond_smt)
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
            case VarAssignExpr(var, expr) if var.sort == BOOL:
                if outlab.frame.enum_vars[var.name] == "FALSE":
                    expr = Not(expr)
                expr = normalized_expr(expr, inlab)
                if expr not in {TRUE, FALSE}:
                    expr_smt = self._expr_to_smt(expr, inlab)
                    constraints.append(expr_smt)
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
            case VarAssignExpr(var, expr) if var.sort.is_enum():
                pass
            case VarAssignExpr(var, expr):
                expr = normalized_expr(expr, inlab)
                if isinstance(expr, Field):
                    field_var = self._data_field(expr.name)
                    expr_smt = self.fragment_factory.field_symbol(field_var, inlab)
                else:
                    expr_smt = self._expr_to_smt(expr, inlab)
                var_smt = self.fragment_factory.var_symbol(var, outlab)
                constraints.append(smt.Equals(var_smt, expr_smt))
                constraints.extend(
                    constraint
                    for constraint in self._internal_equality_constraints(inlab, outlab, exclude_symbols={var_smt})
                )
            case FieldAssignExpr(field, expr) if sort_of(field) == BOOL:
                if outlab.frame.enum_fields[field.name] == "FALSE":
                    expr = Not(expr)
                expr = normalized_expr(expr, inlab)
                if expr not in {TRUE, FALSE}:
                    expr_smt = self._expr_to_smt(expr, inlab)
                    constraints.append(expr_smt)
                constraints.extend(self._internal_equality_constraints(inlab, outlab))
            case FieldAssignExpr(field, expr) if not sort_of(field).is_enum():
                field_var = self._data_field(field.name)
                field_smt = self.fragment_factory.field_symbol(field_var, outlab)
                expr = normalized_expr(expr, inlab)
                expr_smt = self._expr_to_smt(expr, inlab)
                constraints.append(smt.Equals(field_smt, expr_smt))
                constraints.extend(
                    constraint
                    for constraint in self._internal_equality_constraints(inlab, outlab, exclude_symbols={field_smt})
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
            child_key = step.dir.child
            parent = step.in_label
            child = step.out_label
            outlab_prefix = "c"
            inlab_prefix = "p"
        else:
            raise ValueError(f"Invalid direction for external step: {step.dir}")
        data_constraints = list(
            self.fragment_factory.cross_data_constraints(
                parent,
                child,
                child_key,
                parent_variable_prefix="p", child_variable_prefix="c"
            )
        )

        for field in self.fragment_factory.data_fields:
            left = self.fragment_factory.field_symbol(field, step.out_label.origin, prefix=outlab_prefix)
            right = self.fragment_factory.field_symbol(field, step.out_label, prefix=outlab_prefix)
            data_constraints.append(smt.Equals(left, right))
        inlab_app = self.apply(step.in_label, variables_prefix=inlab_prefix)
        outlab_origin_app = self.apply(step.out_label.origin, variables_prefix=outlab_prefix)
        body = smt.And(*data_constraints, inlab_app, outlab_origin_app)
        head = self.apply(step.out_label, variables_prefix=outlab_prefix)
        formula = chc.Clause(body, head)
        return formula

    def chc_IV(self, step: Step) -> FNode:  # noqa: N802
        return self._chc_external(step)

    def chc_V(self, step: Step) -> FNode:  # noqa: N802
        return self._chc_external(step)

    def query(self, lab: Label) -> FNode:
        predicate_application = self.apply(lab)
        return chc.Clause(predicate_application, smt.FALSE())
