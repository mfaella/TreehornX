from dataclasses import dataclass, field
from functools import cached_property, partial
from itertools import chain
from typing import Any, Callable, ClassVar, Iterable, TextIO, cast

import ir.sorts as irs
from chc.core import Label, Pair
from chc.core.dir import Down
from chc.core.event import ERR, LOF, OOM
from ir.expressions import Add, And, Div, Eq, Expr, Ge, Gt, Le, Lt, Mod, Mul, Ne, Negate, Not, Or, Sub, Var
from ir.instructions import FieldAssignExpr, IfGoto, Instruction, VarAssignExpr

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

    def smt2_var_id(self, var: Var, prefix: str) -> str:
        return f"{prefix}_{var.name}"

    def smt2_var_decl(self, var: Var, prefix: str) -> str:
        sort = SMT2FileBuilder.IR_TO_SMT2_SORT[var.sort]
        name = self.smt2_var_id(var, prefix)
        return f"({name} {sort})"

    def sigma_var_decl(self, var: Var, index: int) -> str:
        """sv stands for 'sigma variable'."""
        return self.smt2_var_decl(var, f"sv{index}_")

    def tau_var_decl(self, var: Var, index: int) -> str:
        """tv stands for 'tau variable'."""
        return self.smt2_var_decl(var, f"tv{index}_")

    def sigma_field_decl(self, field: Var, index: int) -> str:
        """sf stands for 'sigma field'."""
        return self.smt2_var_decl(field, f"sf{index}_")

    def tau_field_decl(self, field: Var, index: int) -> str:
        """tf stands for 'tau field'."""
        return self.smt2_var_decl(field, f"tf{index}_")

    def sigma_var_id(self, var: Var, index: int) -> str:
        """sv stands for 'sigma variable'."""
        return self.smt2_var_id(var, f"sv{index}_")

    def tau_var_id(self, var: Var, index: int) -> str:
        """tv stands for 'tau variable'."""
        return self.smt2_var_id(var, f"tv{index}_")

    def sigma_field_id(self, field: Var, index: int) -> str:
        """sf stands for 'sigma field'."""
        return self.smt2_var_id(field, f"sf{index}_")

    def tau_field_id(self, field: Var, index: int) -> str:
        """tf stands for 'tau field'."""
        return self.smt2_var_id(field, f"tf{index}_")

    def sigma_vars_decl(self, index: int) -> Iterable[str]:
        return (self.sigma_var_decl(var, index) for var in self.vars)

    def sigma_fields_decl(self, index: int) -> Iterable[str]:
        return (self.sigma_field_decl(field, index) for field in self.fields)

    def tau_vars_decl(self, index: int) -> Iterable[str]:
        return (self.tau_var_decl(var, index) for var in self.vars)

    def tau_fields_decl(self, index: int) -> Iterable[str]:
        return (self.tau_field_decl(field, index) for field in self.fields)

    def sigma_vars_id(self, index: int) -> Iterable[str]:
        return (self.sigma_var_id(var, index) for var in self.vars)

    def sigma_fields_id(self, index: int) -> Iterable[str]:
        return (self.sigma_field_id(field, index) for field in self.fields)

    def tau_vars_id(self, index: int) -> Iterable[str]:
        return (self.tau_var_id(var, index) for var in self.vars)

    def tau_fields_id(self, index: int) -> Iterable[str]:
        return (self.tau_field_id(field, index) for field in self.fields)

    def expr_to_smt2(self, expr: Expr, id_maker: Callable[[Var], str]) -> str:
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
            case Var(name, sort):
                return id_maker(expr)
            case int() | float():
                return str(expr)
            case Negate() | Mod():
                raise NotImplementedError("Mod operator not supported in SMT2 conversion")
            case Not() | Eq() | Ne() | Lt() | Gt() | Le() | Ge() | Sub() | Div() | And() | Or() | Add() | Mul():
                args = (self.expr_to_smt2(arg, id_maker) for arg in expr.args())
                formatter = op_formatter_map[type(expr)]
                return formatter(*args)
            case _:
                raise RuntimeError(f"Unsupported expression type: {expr}")

    def declare_predicate(self, lab: Label):
        pred_name = f"Lab{lab.id}"
        args_sorts = chain.from_iterable(
            chain(
                (SMT2FileBuilder.IR_TO_SMT2_SORT[var.sort] for var in self.vars),
                (SMT2FileBuilder.IR_TO_SMT2_SORT[field.sort] for field in self.fields),
            )
            for _ in lab.frames
        )
        decl = smt2decl(pred_name, args_sorts)
        self.decls.add(decl)

    def assert_internal_step(self, tau: Label, stmt: Instruction):
        constraints = []
        match stmt:
            case IfGoto(cond, _):
                cond = ppexp(cond, tau)
                cond_smt2 = self.expr_to_smt2(cond, lambda v: self.tau_var_id(v, tau[-1].index))
                constraints = [cond_smt2]
                b = tau[-1].index
                for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                    constraints.append(smt2equals(left, right))
            case VarAssignExpr(var, expr):
                b = tau[-1].index
                expr = ppexp(expr, tau)
                expr_smt2 = self.expr_to_smt2(expr, lambda v: self.tau_var_id(v, tau[b - 1].index))
                constraints = [smt2equals(self.tau_var_id(var, b), expr_smt2)]
                for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                    if left != self.tau_var_id(var, b):
                        constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                    constraints.append(smt2equals(left, right))
            case FieldAssignExpr(field, expr):
                expr = ppexp(expr, tau)
                var: Var = field.ptr.sort.fields[field.name]  # type: ignore
                assert isinstance(var, Var)
                b = tau[-1].index
                expr_smt2 = self.expr_to_smt2(expr, lambda v: self.tau_var_id(v, tau[b - 1].index))
                constraints = [smt2equals(self.tau_field_id(var, b), expr_smt2)]
                for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                    if left != self.tau_field_id(var, b):
                        constraints.append(smt2equals(left, right))
            case _:
                b = tau[-1].index
                constraints: list[str] = []
                for left, right in zip(self.tau_vars_id(b), self.tau_vars_id(b - 1)):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(b), self.tau_fields_id(b - 1)):
                    constraints.append(smt2equals(left, right))
        label_below = Label.make(*tau.frames[:-1])
        pred_below = f"Lab{label_below.id}"
        pred_tau = f"Lab{tau.id}"
        variable_decls = chain.from_iterable(
            chain(self.tau_vars_decl(f.index), self.tau_fields_decl(f.index)) for f in tau.frames
        )
        tau_args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.frames
        )
        below_args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.frames[:-1]
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
        sigma = pair.follower()
        tau = pair.leader()
        constraints: list[str] = []
        # Build equality constraints between sigma and tau variables/fields according to the pair's direction
        for f in sigma.frames:
            assert f.prev is not None
            match f.prev:
                case dir, i if dir == pair.dir():
                    for left, right in zip(self.sigma_vars_id(f.index), self.tau_vars_id(i)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.sigma_fields_id(f.index), self.sigma_fields_id(f.index - 1)):
                        constraints.append(smt2equals(left, right))
                case _:
                    continue
        for f in tau.frames:
            assert f.prev is not None
            match f.prev:
                case dir, i if dir == pair.rev_dir():
                    for left, right in zip(self.tau_vars_id(f.index), self.sigma_vars_id(i)):
                        constraints.append(smt2equals(left, right))
                    for left, right in zip(self.tau_fields_id(f.index), self.tau_fields_id(f.index - 1)):
                        constraints.append(smt2equals(left, right))
                case _:
                    continue
        below = Label.make(*tau.frames[:-1])
        pred_below = f"Lab{below.id}"
        pred_sigma = f"Lab{sigma.id}"
        pred_tau = f"Lab{tau.id}"
        # Declarations for all sigma and tau variables/fields
        variable_decls = chain.from_iterable(
            chain(
                (self.sigma_vars_decl(f.index) for f in sigma.frames),
                (self.sigma_fields_decl(f.index) for f in sigma.frames),
                (self.tau_vars_decl(f.index) for f in tau.frames),
                (self.tau_fields_decl(f.index) for f in tau.frames),
            )
        )
        # Predicate arguments (ids)
        sigma_args = chain.from_iterable(
            chain(self.sigma_vars_id(f.index), self.sigma_fields_id(f.index)) for f in sigma.frames
        )
        tau_args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.frames
        )
        below_args = chain.from_iterable(
            chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in tau.frames[:-1]
        )
        # Build the SMT2 string
        clause = smt2assert(
            smt2forall(
                variable_decls,
                smt2implies(
                    smt2and(
                        *smt2predicate(pred_below, below_args),
                        *smt2predicate(pred_sigma, sigma_args),
                        *constraints,
                    ),
                    smt2predicate(pred_tau, tau_args),
                ),
            )
        )
        self.chcs.add(clause)

    def assert_fact(self, lab: Label):
        pred = f"Lab{lab.id}"
        idx = lab[-1].index
        variable_decls = chain(self.tau_vars_decl(idx), self.tau_fields_decl(idx))
        args = chain(self.tau_vars_id(idx), self.tau_fields_id(idx))
        fact = smt2assert(smt2forall(variable_decls, smt2predicate(pred, args)))
        self.chcs.add(fact)

    def assert_query(self, lab: Label) -> str:
        assert isinstance(lab[-1].event, (OOM, ERR, LOF))
        pred = f"Lab{lab.id}"
        variable_decls = chain.from_iterable(
            chain(self.tau_vars_decl(f.index), self.tau_fields_decl(f.index)) for f in lab.frames
        )
        args = chain.from_iterable(chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in lab.frames)
        # Assert the negation of the predicate for all variables (SMT2)
        query = smt2assert(smt2forall(variable_decls, smt2implies(smt2predicate(pred, args), smt2false())))
        match lab[-1].event:
            case OOM():
                self.oom_queries.add(query)
            case ERR():
                self.err_qeueries.add(query)
            case LOF():
                self.lof_queries.add(query)

    def _dump(self, stream: TextIO, queries: set[str]):
        stream.write("(set-logic HORN)\n")
        for decl in self.decls:
            stream.write(f"{decl}\n")
        for chc in self.chcs:
            stream.write(f"{chc}\n")
        for query in queries:
            stream.write(f"{query}\n")
        stream.write("(check-sat)\n")

    def dump_checksat_err(self, stream: TextIO):
        queries = self.err_qeueries
        self._dump(stream, queries)

    def dump_checksat_oom(self, stream: TextIO):
        queries = self.oom_queries
        self._dump(stream, queries)

    def dump_checksat_lof(self, stream: TextIO):
        queries = self.lof_queries
        self._dump(stream, queries)

    def dump_checksat_all(self, stream: TextIO):
        queries = self.err_qeueries | self.oom_queries | self.lof_queries
        self._dump(stream, queries)
