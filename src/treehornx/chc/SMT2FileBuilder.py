from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property, partial
from itertools import chain
from typing import Any, Callable, ClassVar, Iterable, Sequence, TextIO, cast

import treehornx.ir.sorts as irs
from treehornx.ir.expressions import (
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
    Sub,
    Var,
)
from treehornx.ir.instructions import FieldAssignExpr, IfGoto, Instruction, VarAssignExpr

from .core import Label, Pair
from .core.dir import Down
from .core.event import ERR, LOF, OOM
from .ppexp import ppexp


def smt2assert(formula: str) -> str:
    return f"(assert {formula})"


def smt2forall(variables_decls: Iterable[str], formula: str) -> str:
    return f"(forall ({' '.join(variables_decls)}) {formula})"


def smt2operator(op: str, args: Iterable[str]) -> str:
    return f"({op} {' '.join(args)})"


def smt2equals(left: str, right: str) -> str:
    return smt2operator("=", [left, right])


def smt2not_equals(left: str, right: str) -> str:
    return smt2not(smt2equals(left, right))


def smt2lt(left: str, right: str) -> str:
    return smt2operator("<", [left, right])


def smt2gt(left: str, right: str) -> str:
    return smt2operator(">", [left, right])


def smt2le(left: str, right: str) -> str:
    return smt2operator("<=", [left, right])


def smt2ge(left: str, right: str) -> str:
    return smt2operator(">=", [left, right])


def smt2and(*conjuncts: str) -> str:
    return smt2operator("and", conjuncts)


def smt2or(*disjuncts: str) -> str:
    return smt2operator("or", disjuncts)


def smt2implies(antecedent: str, consequent: str) -> str:
    return smt2operator("=>", [antecedent, consequent])


def smt2not(arg: str) -> str:
    return smt2operator("not", [arg])


def smt2plus(*args: str) -> str:
    return smt2operator("+", args)


def smt2minus(left: str, right: str) -> str:
    return smt2operator("-", [left, right])


def smt2times(*args: str) -> str:
    return smt2operator("*", args)


def smt2div(left: str, right: str) -> str:
    return smt2operator("/", [left, right])


def smt2predicate(pred_name: str, args: Iterable[str]) -> str:
    return f"({pred_name} {' '.join(args)})"


def smt2decl(pred_name: str, args_sorts: Iterable[str]) -> str:
    return f"(declare-fun {pred_name} ({' '.join(args_sorts)}) Bool)"


def smt2false() -> str:
    return "false"


def smt2true() -> str:
    return "true"


class ExitCodeKind(Enum):
    ERR = 1
    OOM = 2
    LABEL_OVERFLOW = 3


@dataclass
class SMT2FileBuilder:
    vars: set[Var]
    fields: set[Var]
    chcs: set[str] = field(init=False, default_factory=lambda: set())
    decls: set[str] = field(init=False, default_factory=lambda: set())
    oom_queries: set[str] = field(init=False, default_factory=lambda: set())
    err_qeueries: set[str] = field(init=False, default_factory=lambda: set())
    lof_queries: set[str] = field(init=False, default_factory=lambda: set())

    IR_TO_SMT2_SORT: ClassVar[dict[irs.Sort, Any]] = {irs.INT: "Int", irs.REAL: "Real"}

    def smt2_var_id(self, name: str, prefix: str) -> str:
        return f"{prefix}_{name}"

    def smt2_var_decl(self, var: Var, prefix: str) -> str:
        sort = SMT2FileBuilder.IR_TO_SMT2_SORT[var.sort]
        name = self.smt2_var_id(var.name, prefix)
        return f"({name} {sort})"

    def sigma_var_decl(self, var: Var, index: int) -> str:
        """sv stands for 'sigma variable'."""
        return self.smt2_var_decl(var, f"sv{index}")

    def tau_var_decl(self, var: Var, index: int) -> str:
        """tv stands for 'tau variable'."""
        return self.smt2_var_decl(var, f"tv{index}")

    def sigma_field_decl(self, field: Var, index: int) -> str:
        """sf stands for 'sigma field'."""
        return self.smt2_var_decl(field, f"sf{index}")

    def tau_field_decl(self, field: Var, index: int) -> str:
        """tf stands for 'tau field'."""
        return self.smt2_var_decl(field, f"tf{index}")

    def sigma_var_id(self, var: str, index: int) -> str:
        """sv stands for 'sigma variable'."""
        return self.smt2_var_id(var, f"sv{index}")

    def tau_var_id(self, var: str, index: int) -> str:
        """tv stands for 'tau variable'."""
        assert isinstance(var, str)
        assert var != "value"
        return self.smt2_var_id(var, f"tv{index}")

    def sigma_field_id(self, field: str, index: int) -> str:
        """sf stands for 'sigma field'."""
        return self.smt2_var_id(field, f"sf{index}")

    def tau_field_id(self, field: str, index: int) -> str:
        """tf stands for 'tau field'."""
        return self.smt2_var_id(field, f"tf{index}")

    def sigma_vars_decl(self, index: int) -> Iterable[str]:
        return (self.sigma_var_decl(var, index) for var in self.vars)

    def sigma_fields_decl(self, index: int) -> Iterable[str]:
        return (self.sigma_field_decl(field, index) for field in self.fields)

    def tau_vars_decl(self, index: int) -> Iterable[str]:
        return (self.tau_var_decl(var, index) for var in self.vars)

    def tau_fields_decl(self, index: int) -> Iterable[str]:
        return (self.tau_field_decl(field, index) for field in self.fields)

    def sigma_vars_id(self, index: int) -> Iterable[str]:
        return (self.sigma_var_id(var.name, index) for var in self.vars)

    def sigma_fields_id(self, index: int) -> Iterable[str]:
        return (self.sigma_field_id(field.name, index) for field in self.fields)

    def tau_vars_id(self, index: int) -> Iterable[str]:
        return (self.tau_var_id(var.name, index) for var in self.vars)

    def tau_fields_id(self, index: int) -> Iterable[str]:
        return (self.tau_field_id(field.name, index) for field in self.fields)

    def expr_to_smt2(self, expr: Expr, var_id_maker: Callable[[str], str], field_id_maker: Callable[[str], str]) -> str:
        op_formatter_map: dict[type, Callable[..., str]] = {
            # unaries
            Not: smt2not,
            # binaries
            Eq: smt2equals,
            Ne: smt2not_equals,
            Gt: smt2gt,
            Lt: smt2lt,
            Ge: smt2ge,
            Le: smt2le,
            Sub: smt2minus,
            Div: smt2div,
            # variadics
            And: smt2and,
            Or: smt2or,
            Add: smt2plus,
            Mul: smt2times,
        }
        match expr:
            case Var(name, _):
                return var_id_maker(name)
            case Field(_, name):
                return field_id_maker(name)
            case int() | float():
                return str(expr)
            case Negate() | Mod():
                raise NotImplementedError("Mod operator not supported in SMT2 conversion")
            case Not() | Eq() | Ne() | Lt() | Gt() | Le() | Ge() | Sub() | Div() | And() | Or() | Add() | Mul():
                args = (self.expr_to_smt2(arg, var_id_maker, field_id_maker) for arg in expr.args())
                formatter = op_formatter_map[type(expr)]
                return formatter(*args)
            case EnumConst(sort, value) if sort == irs.BOOL:
                return smt2true() if value == TRUE else smt2false()
            case _:
                raise RuntimeError(f"Unsupported expression type: {expr}")

    def declare_predicate(self, lab: Label):
        pred_name = f"Lab{lab.id}"
        args_sorts = chain.from_iterable(
            chain(
                (SMT2FileBuilder.IR_TO_SMT2_SORT[var.sort] for var in self.vars),
                (SMT2FileBuilder.IR_TO_SMT2_SORT[field.sort] for field in self.fields),
            )
            for _ in lab.backward_iter()
        )
        decl = smt2decl(pred_name, args_sorts)
        self.decls.add(decl)

    def assert_internal_step(self, tau: Label, stmt: Instruction):
        if tau.id == 358:
            pass
        self.declare_predicate(tau)
        constraints = []

        if isinstance(tau[-1].event, (OOM, ERR, LOF)):
            variable_decls = chain.from_iterable(
                chain(self.tau_vars_decl(f.index), self.tau_fields_decl(f.index)) for f in tau.backward_iter()
            )
            args = chain.from_iterable(
                chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.backward_iter()
            )
            pred = f"Lab{tau.id}"
            query = smt2assert(smt2forall(variable_decls, smt2implies(smt2predicate(pred, args), smt2false())))
            match tau[-1].event:
                case OOM():
                    self.oom_queries.add(query)
                case ERR():
                    self.err_qeueries.add(query)
                case LOF():
                    self.lof_queries.add(query)

        else:

            def var_id_maker(v: str):
                return self.tau_var_id(v, tau[-1].index)

            def field_id_maker(f: str):
                return self.tau_field_id(f, tau[-1].index)

            match stmt:
                case IfGoto(cond, _):
                    cond = ppexp(cond, tau)
                    cond_smt2 = self.expr_to_smt2(
                        cond,
                        var_id_maker,
                        field_id_maker,
                    )
                    constraints = [cond_smt2]
                    b = tau[-1].index
                    for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                        constraints.append(smt2equals(left, right))
                case VarAssignExpr(var, expr):
                    b = tau[-1].index
                    expr = ppexp(expr, tau)
                    expr_smt2 = self.expr_to_smt2(expr, var_id_maker, field_id_maker)
                    constraints = [smt2equals(self.tau_var_id(var.name, b), expr_smt2)]
                    for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                        if left != self.tau_var_id(var.name, b):
                            constraints.append(smt2equals(left, right))
                    for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                        constraints.append(smt2equals(left, right))
                case FieldAssignExpr(field, expr):
                    expr = ppexp(expr, tau)
                    var: Var = field.ptr.sort.fields[field.name]  # type: ignore
                    assert isinstance(var, Var)
                    b = tau[-1].index
                    expr_smt2 = self.expr_to_smt2(expr, var_id_maker, field_id_maker)
                    constraints = [smt2equals(self.tau_field_id(var.name, b), expr_smt2)]
                    for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                        if left != self.tau_field_id(var.name, b):
                            constraints.append(smt2equals(left, right))
                case _:
                    b = tau[-1].index
                    constraints: list[str] = []
                    for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                        constraints.append(smt2equals(left, right))
            label_below = tau.origin
            pred_below = f"Lab{label_below.id}"
            pred_tau = f"Lab{tau.id}"
            variable_decls = chain.from_iterable(
                chain(self.tau_vars_decl(f.index), self.tau_fields_decl(f.index)) for f in tau.backward_iter()
            )
            tau_args = chain.from_iterable(
                chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.backward_iter()
            )
            below_args = chain.from_iterable(
                chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.origin.backward_iter()
            )
            clause = smt2assert(
                smt2forall(
                    variable_decls,
                    smt2implies(
                        smt2and(smt2predicate(pred_below, below_args), *constraints),
                        smt2predicate(pred_tau, tau_args),
                    ),
                )
            )
            self.chcs.add(clause)

    def assert_external_step(self, pair: Pair):
        if pair.leader().id == 183:
            pass
        sigma = pair.follower()
        tau = pair.leader()
        self.declare_predicate(sigma)
        self.declare_predicate(tau)
        constraints: list[str] = []
        # Build equality constraints between sigma and tau variables/fields according to the pair's direction
        for f in sigma.slice(1):
            match f.prev:
                case dir, i if dir == pair.rev_dir():
                    for left, right in zip(self.sigma_vars_id(f.index), self.tau_vars_id(i)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.sigma_fields_id(f.index), self.sigma_fields_id(f.index - 1)):
                        constraints.append(smt2equals(left, right))
                case _:
                    continue
        for f in tau.slice(1):
            match f.prev:
                case dir, i if dir == pair.dir():
                    for left, right in zip(self.tau_vars_id(f.index), self.sigma_vars_id(i)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.tau_fields_id(f.index), self.tau_fields_id(f.index - 1)):
                        constraints.append(smt2equals(left, right))
                case _:
                    continue
        below = tau.origin
        pred_below = f"Lab{below.id}"
        pred_sigma = f"Lab{sigma.id}"
        pred_tau = f"Lab{tau.id}"
        # Declarations for all sigma and tau variables/fields
        variable_decls = chain.from_iterable(
            chain(
                (self.sigma_vars_decl(f.index) for f in sigma.backward_iter()),
                (self.sigma_fields_decl(f.index) for f in sigma.backward_iter()),
                (self.tau_vars_decl(f.index) for f in tau.backward_iter()),
                (self.tau_fields_decl(f.index) for f in tau.backward_iter()),
            )
        )
        # Predicate arguments (ids)
        sigma_args = chain.from_iterable(
            chain(self.sigma_vars_id(f.index), self.sigma_fields_id(f.index)) for f in sigma.backward_iter()
        )
        tau_args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.backward_iter()
        )
        below_args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.origin.backward_iter()
        )
        # Build the SMT2 string
        clause = smt2assert(
            smt2forall(
                variable_decls,
                smt2implies(
                    smt2and(
                        smt2predicate(pred_below, below_args),
                        smt2predicate(pred_sigma, sigma_args),
                        *constraints,
                    ),
                    smt2predicate(pred_tau, tau_args),
                ),
            )
        )
        self.chcs.add(clause)

    def assert_fact(self, lab: Label):
        self.declare_predicate(lab)
        pred = f"Lab{lab.id}"
        variable_decls = chain.from_iterable(
            chain(self.tau_vars_decl(f.index), self.tau_fields_decl(f.index)) for f in lab.backward_iter()
        )
        args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in lab.backward_iter()
        )
        fact = smt2assert(smt2forall(variable_decls, smt2predicate(pred, args)))
        self.chcs.add(fact)

    def dump(
        self,
        stream: TextIO,
        exit_code: ExitCodeKind,
        *,
        logic: str = "HORN",
        check_sat: bool = False,
        get_model: bool = False,
        exit: bool = False,
    ):
        stream.write(f"(set-logic {logic})\n")
        for decl in self.decls:
            stream.write(f"{decl}\n")
        for chc in self.chcs:
            stream.write(f"{chc}\n")
        if exit_code == ExitCodeKind.ERR:
            queries = self.err_qeueries
        elif exit_code == ExitCodeKind.OOM:
            queries = self.oom_queries
        elif exit_code == ExitCodeKind.LABEL_OVERFLOW:
            queries = self.lof_queries
        else:
            queries: set[str] = set()
        for query in queries:
            stream.write(f"{query}\n")

        if check_sat:
            stream.write(f"(check-sat)\n")

        if get_model:
            stream.write(f"(get-model)\n")

        if exit:
            stream.write(f"(exit)\n")
