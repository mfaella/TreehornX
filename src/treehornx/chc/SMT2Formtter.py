from dataclasses import dataclass
from functools import cached_property
from itertools import chain
from typing import Any, Iterable

import ir.sorts as irs
from chc.core import Label, Pair
from chc.core.dir import Down
from ir.expressions import Var, Expr, And, Or, Not, Eq, Ne, Gt, Lt, Ge, Le, Add, Sub, Mul, Div, Mod
from ir.instructions import Instruction, IfGoto, FieldAssignExpr, VarAssignExpr
from pysmt.fnode import FNode
from pysmt.shortcuts import BOOL, GT, INT, REAL, And, Equals, ForAll, Function, FunctionType, Implies, Symbol, Not, Or, LT, GE, LE, Plus, Minus, Times, Div as smtDiv
from pysmt.typing import PySMTType

from .ppexp import ppexp

IR_TO_PYSMT_SORT: dict[irs.Sort, Any] = {irs.INT: INT, irs.REAL: REAL}


def make_symbol(var: Var, prefix: str) -> FNode:
    sort = IR_TO_PYSMT_SORT[var.sort]
    name = f"{prefix}_{var.name}"
    symbol = Symbol(name, sort)
    return symbol


@dataclass
class ChcBuilder:
    vars: set[Var]
    fields: set[Var]

    def sigma_var(self, var: Var, index: int) -> FNode:
        """sv stands for 'sigma variable'."""
        return make_symbol(var, f"sv{index}_")

    def tau_var(self, var: Var, index: int) -> FNode:
        """tv stands for 'tau variable'."""
        return make_symbol(var, f"tv{index}_")

    def sigma_field(self, field: Var, index: int) -> FNode:
        """sf stands for 'sigma field'."""
        return make_symbol(field, f"sf{index}_")

    def tau_field(self, field: Var, index: int) -> FNode:
        """tf stands for 'tau field'."""
        return make_symbol(field, f"tf{index}_")

    def sigma_vars_symbols(self, index: int) -> Iterable[FNode]:
        return (self.sigma_var(var, index) for var in self.vars)

    def sigma_fields_symbols(self, index: int) -> Iterable[FNode]:
        return (self.sigma_field(field, index) for field in self.fields)

    def tau_vars_symbols(self, index: int) -> Iterable[FNode]:
        return (self.tau_var(var, index) for var in self.vars)

    def tau_fields_symbols(self, index: int) -> Iterable[FNode]:
        return (self.tau_field(field, index) for field in self.fields)

    def predicate_signature(self, label: Label) -> PySMTType:
        sorts = []
        for _ in label.frames:
            for var in self.vars:
                sorts.append(IR_TO_PYSMT_SORT[var.sort])
            for field in self.fields:
                sorts.append(IR_TO_PYSMT_SORT[field.sort])
        return FunctionType(BOOL, sorts)

    def expr_to_pysmt(self, expr: Expr, lab: Label) -> FNode:
        match expr:
            case Var(name, sort):
                return self.tau_var(Var(name, sort), lab[-2].index)
            case Not(e):
                return Not(self.expr_to_pysmt(e, lab))
            case And():
                return And(*(self.expr_to_pysmt(arg, lab) for arg in expr.args()))
            case Or():
                return Or(*(self.expr_to_pysmt(arg, lab) for arg in expr.args()))
            case Eq(lhs, rhs):
                return Equals(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab))
            case Ne(lhs, rhs):
                return Not(Equals(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab)))
            case Gt(lhs, rhs):
                return GT(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab))
            case Lt(lhs, rhs):
                return LT(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab))
            case Ge(lhs, rhs):
                return GE(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab))
            case Le(lhs, rhs):
                return LE(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab))
            case Add():
                return Plus(*(self.expr_to_pysmt(arg, lab) for arg in expr.args()))
            case Sub():
                args = list(expr.args())
                return Minus(self.expr_to_pysmt(args[0], lab), self.expr_to_pysmt(args[1], lab))
            case Mul():
                return Times(*(self.expr_to_pysmt(arg, lab) for arg in expr.args()))
            case Div(lhs, rhs):
                return smtDiv(self.expr_to_pysmt(lhs, lab), self.expr_to_pysmt(rhs, lab))
            case Mod(lhs, rhs):
                # No direct Mod in pysmt, so we express it via other operations
                lhs_pysmt = self.expr_to_pysmt(lhs, lab)
                rhs_pysmt = self.expr_to_pysmt(rhs, lab)
                return Minus(
                    lhs_pysmt,
                    Times(
                        smtDiv(
                            lhs_pysmt,
                            rhs_pysmt
                        )
                        , rhs_pysmt
                    )
                )
            case _:
                raise RuntimeError(f"Unsupported expression type: {expr}")

    def assert_internal_step(self, tau: Label, stmt: Instruction) -> FNode:
        constraints = []
        match stmt:
            case IfGoto(cond, _):
                cond_smt = self.expr_to_pysmt(cond, tau)
                constraints = [cond_smt]
                b = tau[-1].index
                for left, right in zip(self.tau_vars_symbols(b), self.tau_vars_symbols(b - 1)):
                    constraints.append(Equals(left, right))
                for left, right in zip(self.tau_fields_symbols(b), self.tau_fields_symbols(b - 1)):
                    constraints.append(Equals(left, right))
            case VarAssignExpr(var, expr):
                b = tau[-1].index
                expr_smt = self.expr_to_pysmt(expr, tau)
                constraints = [Equals(self.tau_var(var, b), expr_smt)]
                for left, right in zip(self.tau_vars_symbols(b), self.tau_vars_symbols(b - 1)):
                    if left != self.tau_var(var, b):
                        constraints.append(Equals(left, right))
                for left, right in zip(self.tau_fields_symbols(b), self.tau_fields_symbols(b - 1)):
                    constraints.append(Equals(left, right))
            case FieldAssignExpr(field, expr):
                b = tau[-1].index
                expr_smt = self.expr_to_pysmt(expr, tau)
                constraints = [Equals(self.tau_field(field, b), expr_smt)]
                for left, right in zip(self.tau_vars_symbols(b), self.tau_vars_symbols(b - 1)):
                    constraints.append(Equals(left, right))
                for left, right in zip(self.tau_fields_symbols(b), self.tau_fields_symbols(b - 1)):
                    if left != self.tau_field(field, b):
                        constraints.append(Equals(left, right))
            case _:
                b = tau[-1].index
                for left, right in zip(self.tau_vars_symbols(b), self.tau_vars_symbols(b - 1)):
                    constraints.append(Equals(left, right))
                for left, right in zip(self.tau_fields_symbols(b), self.tau_fields_symbols(b - 1)):
                    constraints.append(Equals(left, right))
        label_below = Label.make(*tau.frames[:-1])
        pred_below = Symbol(f"Lab{label_below.id}", self.predicate_signature(label_below))
        pred_tau = Symbol(f"Lab{tau.id}", self.predicate_signature(tau))
        variables = []
        for f in tau.frames:
            variables.extend(self.tau_vars_symbols(f.index))
            variables.extend(self.tau_fields_symbols(f.index))
        tau_args = variables
        below_args = []
        for f in tau.frames[:-1]:
            below_args.extend(self.tau_vars_symbols(f.index))
            below_args.extend(self.tau_fields_symbols(f.index))
        return ForAll(
            variables,
            Implies(
                And(
                    Function(pred_below, below_args),
                    *constraints
                ),
                Function(pred_tau, tau_args)
            )
        )


    def assert_external_step(self, pair: Pair) -> FNode:
        sigma = pair.follower()
        tau = pair.leader()
        constraints = []
        for f in sigma.frames:
            assert f.prev is not None
            match f.prev:
                case dir, i if dir == pair.dir():
                    for left, right in zip(self.sigma_vars_symbols(f.index), self.tau_vars_symbols(i)):
                        constraints.append(Equals(left, right))
                    for left, right in zip(self.sigma_fields_symbols(f.index), self.sigma_fields_symbols(f.index - 1)):
                        constraints.append(Equals(left, right))
                case _:
                    continue
        for f in tau.frames:
            assert f.prev is not None
            match f.prev:
                case dir, i if dir == pair.rev_dir():
                    for left, right in zip(self.tau_vars_symbols(f.index), self.sigma_vars_symbols(i)):
                        constraints.append(Equals(left, right))
                    for left, right in zip(self.tau_fields_symbols(f.index), self.tau_fields_symbols(f.index - 1)):
                        constraints.append(Equals(left, right))
                case _:
                    continue
        label_below = Label.make(*tau.frames[:-1])
        pred_below = Symbol(f"Lab{label_below.id}", self.predicate_signature(label_below))
        pred_sigma = Symbol(f"Lab{sigma.id}", self.predicate_signature(sigma))
        pred_tau = Symbol(f"Lab{tau.id}", self.predicate_signature(tau))

        variables = []
        sigma_args = []
        for f in sigma.frames:
            variables.extend(self.sigma_vars_symbols(f.index))
            variables.extend(self.sigma_fields_symbols(f.index))
            sigma_args.extend(self.sigma_vars_symbols(f.index))
            sigma_args.extend(self.sigma_fields_symbols(f.index))
        tau_args = []
        below_args = []
        for f in tau.frames:
            variables.extend(self.tau_vars_symbols(f.index))
            variables.extend(self.tau_fields_symbols(f.index))
            tau_args.extend(self.tau_vars_symbols(f.index))
            tau_args.extend(self.tau_fields_symbols(f.index))
            if f.index < tau.frames[-1].index:
                below_args.extend(self.tau_vars_symbols(f.index))
                below_args.extend(self.tau_fields_symbols(f.index))

        return ForAll(
            variables,
            Implies(
                And(
                    Function(pred_below, below_args),
                    Function(pred_sigma, sigma_args),
                    *constraints
                )
                Function(pred_tau, tau_args)
            )
        )

    def assert_fact(self, lab: Label) -> FNode:
        pred = Symbol(f"Lab{lab.id}", self.predicate_signature(lab))
        variables = [*self.tau_vars_symbols(lab[-1].index), *self.tau_fields_symbols(lab[-1].index)]
        args = variables
        return ForAll(
            variables,
            Function(
                pred,
                args
            )
        )

    def query(self, lab: Label) -> FNode:
        pred = Symbol(f"Lab{lab.id}", self.predicate_signature(lab))
        variables = chain(self.tau_vars_symbols(lab[-1].index), self.tau_fields_symbols(lab[-1].index))
        args = variables
        return Not(
            Function(
                pred,
                args
            )
        )
