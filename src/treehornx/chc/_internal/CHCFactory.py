from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from itertools import islice
from typing import Callable, Iterable

from treehornx.chc._internal.smtlib import *
from treehornx.enum_labels import LaceOverApproximation, Step
from treehornx.enum_labels.core import Label
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
class CHCFactory:
    function: Function
    tree_node_sort: Struct
    lace_over_approx: LaceOverApproximation

    @cached_property
    def ir_type_to_smt2_sort(self) -> dict[Sort, str]:
        return {INT: intType(), REAL: realType()}

    def _data_variables(self) -> Iterable[Var]:
        return (v for v in self.function.vars if not (v.sort.is_enum() or v.sort.is_ptr()))

    def _data_fields(self) -> Iterable[Var]:
        return (v for v in self.tree_node_sort.fields.values() if not (v.sort.is_enum() or v.sort.is_ptr()))

    def _id(self, lab: Label) -> int:
        return self.lace_over_approx.id(lab)

    def _var_name(self, var: Var, lab: Label, prefix: str = "") -> str:
        var_name = f"{prefix}{self._id(lab)}_{var.name}"
        return var_name

    def _last_frame_bounded_vars(self, lab: Label) -> Iterable[tuple[str, str]]:
        for var in self._data_variables():
            yield self._var_name(var, lab, prefix="v"), self.ir_type_to_smt2_sort[var.sort]
        for field in self._data_fields():
            yield self._var_name(field, lab, prefix="f"), self.ir_type_to_smt2_sort[field.sort]

    def _label_bounded_vars(self, lab: Label) -> Iterable[tuple[str, str]]:
        for origin in lab.iter_origins():
            yield from self._last_frame_bounded_vars(origin)

    def predicate(self, lab: Label) -> tuple[str, str, tuple[str, ...]]:
        predicate_name = f"Lab{self._id(lab)}"
        bounded_vars_types = tuple(ty for _, ty in self._label_bounded_vars(lab))
        return_type = boolType()
        predicate = (predicate_name, return_type, bounded_vars_types)
        return predicate

    def _apply_predicate(self, lab: Label) -> str:
        predicate = self.predicate(lab)
        bounded_variables = tuple(self._label_bounded_vars(lab))
        predicate_application_result = predicate_application(predicate[0], (var for var, _ in bounded_variables))
        return predicate_application_result

    def _fact(self, lab: Label) -> str:
        bounded_variables = self._label_bounded_vars(lab)
        predicate_application = self._apply_predicate(lab)
        return forall(bounded_variables, predicate_application)

    def chc_I(self, lab: Label) -> str:  # noqa: N802
        return self._fact(lab)

    def chc_II(self, lab: Label) -> str:  # noqa: N802
        return self._fact(lab)

    def _equality_constraints(self, inlab: Label, outlab: Label, exclude_symbols: set[str] = set()) -> Iterable[str]:
        for left, right in zip(self._last_frame_bounded_vars(inlab), self._last_frame_bounded_vars(outlab)):
            left_name, right_name = left[0], right[0]
            if left_name not in exclude_symbols and right_name not in exclude_symbols:
                yield equals(left_name, right_name)

    def _expr_to_smt(self, expr: Expr, inlab: Label) -> str:
        op_converter_map: dict[type, Callable[..., str]] = {
            # unaries
            Not: not_,
            # binaries
            Eq: equals,
            Ne: not_equals,
            Gt: gt,
            Lt: lt,
            Ge: ge,
            Le: le,
            Sub: minus,
            Div: div,
            # variadics
            And: and_,
            Or: or_,
            Add: plus,
            Mul: times,
        }
        match expr:
            case Var(name, _):
                return self._var_name(expr, inlab, prefix="v")
            case Field(_, name):
                var = self.tree_node_sort.fields[name]
                return self._var_name(var, inlab, prefix="f")
            case int():
                return int_(expr)
            case float():
                return real_(expr)
            case Not() | Eq() | Ne() | Lt() | Gt() | Le() | Ge() | Sub() | Div() | And() | Or() | Add() | Mul():
                args = (self._expr_to_smt(arg, inlab) for arg in expr.args())
                converter = op_converter_map[type(expr)]
                return converter(*args)
            case EnumConst() | PtrIsPtr() | PtrIsNil():
                raise RuntimeError(f"Normalized expressions should not contain {type(expr).__name__}")
            case Negate() | Mod():
                raise NotImplementedError("Mod operator not supported in SMT2 conversion")

    def _internal_data_constraints(self, inlab: Label, outlab: Label) -> Iterable[str]:
        stmt = self.function.instructions[inlab.frame.pc]
        constraints: list[str] = []

        if self.lace_over_approx.id(outlab) == 47:
            pass
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
                    expr_smt = self._var_name(field_var, inlab, prefix="f")
                else:
                    expr_smt = self._expr_to_smt(expr, inlab)
                var_smt = self._var_name(var, outlab, prefix="v")
                constraints.append(equals(var_smt, expr_smt))
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
                field_smt = self._var_name(field_var, outlab, prefix="f")
                expr = normalized_expr(expr, inlab.frame)
                expr_smt = self._expr_to_smt(expr, inlab)
                constraints.append(equals(field_smt, expr_smt))
                constraints.extend(
                    constraint for constraint in self._equality_constraints(inlab, outlab, exclude_symbols={field_smt})
                )
            case _:
                constraints.extend(self._equality_constraints(inlab, outlab))
        return iter(constraints)

    def _step_chc(self, head_lab: Label, body_labs: Iterable[Label], data_constraints: Iterable[str]):
        body_labs = tuple(body_labs)
        bounded_variables: list[tuple[str, str]] = []
        bounded_variables.extend(self._label_bounded_vars(head_lab))
        for body_lab in body_labs:
            bounded_variables.extend(self._label_bounded_vars(body_lab))

        bounded_variables_set = set(bounded_variables)
        body_predicates_application = tuple(self._apply_predicate(body_lab) for body_lab in body_labs)
        data_constraints = tuple(data_constraints)
        body = and_(*body_predicates_application, *data_constraints)
        head = self._apply_predicate(head_lab)
        formula = forall(
            bounded_variables_set,
            implies(body, head),
        )
        return formula

    def chc_III(self, step: Step) -> str:  # noqa: N802
        data_constraints = self._internal_data_constraints(step.in_label, step.out_label)
        formula = self._step_chc(step.out_label, [step.in_label], data_constraints)
        return formula

    def _chc_external(self, step: Step) -> str:
        assert step.out_label.frame.prev is not None
        assert step.out_label.origin is not None
        data_constraints: list[str] = []
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

    def chc_IV(self, step: Step) -> str:  # noqa: N802
        return self._chc_external(step)

    def chc_V(self, step: Step) -> str:  # noqa: N802
        return self._chc_external(step)

    def query(self, lab: Label) -> str:
        variables = tuple(self._label_bounded_vars(lab))
        predicate_application = self._apply_predicate(lab)
        return forall(
            variables,
            implies(
                predicate_application,
                false(),
            ),
        )
