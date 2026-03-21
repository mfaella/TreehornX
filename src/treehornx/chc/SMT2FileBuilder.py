from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from itertools import chain
from typing import Any, Callable, ClassVar, Iterable, Sequence, TextIO

from treehornx.enum_labels.knitter.utils import normalized_expr
from treehornx.enum_labels.LabelDB import LabelDB
from treehornx.enum_labels.PairDB import PairDB
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
    PtrIsPtr,
    Sub,
    Var,
    normalized,
    sort_of,
)
from treehornx.ir.function import Function
from treehornx.ir.instructions import FieldAssignExpr, IfGoto, Instruction, VarAssignExpr
from treehornx.ir.sorts import BOOL, INT, REAL, Sort, Struct

from ..enum_labels.core import Label
from ..enum_labels.core.Dir import Down
from ..enum_labels.core.Event import ERR, LOF, OOM
from ..enum_labels.knitter.Pair import Pair


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
    function: Function
    root_sort: Struct
    labels: LabelDB
    pairs: PairDB
    chcs: set[str] = field(init=False, default_factory=lambda: set())
    decls: set[str] = field(init=False, default_factory=lambda: set())
    oom_queries: set[str] = field(init=False, default_factory=lambda: set())
    err_qeueries: set[str] = field(init=False, default_factory=lambda: set())
    lof_queries: set[str] = field(init=False, default_factory=lambda: set())

    @cached_property
    def vars(self) -> Sequence[Var]:
        return tuple(var for var in self.function.vars if not var.sort.is_enum())

    @cached_property
    def fields(self) -> Sequence[Var]:
        return tuple(v for v in self.root_sort.fields.values() if not (sort_of(v).is_ptr() or sort_of(v).is_enum()))

    IR_TO_SMT2_SORT: ClassVar[dict[Sort, Any]] = {INT: "Int", REAL: "Real"}

    def id(self, lab: Label) -> int:
        return self.labels.id(lab)

    def smt2_var_id(self, name: str, prefix: str) -> str:
        return f"{prefix}_{name}"

    def smt2_var_decl(self, var: Var, prefix: str) -> str:
        sort = SMT2FileBuilder.IR_TO_SMT2_SORT[var.sort]
        name = self.smt2_var_id(var.name, prefix)
        return f"({name} {sort})"

    def sigma_var_decl(self, var: Var, id: int) -> str:
        """sv stands for 'sigma variable'."""
        return self.smt2_var_decl(var, f"sv{id}")

    def tau_var_decl(self, var: Var, id: int) -> str:
        """tv stands for 'tau variable'."""
        return self.smt2_var_decl(var, f"tv{id}")

    def sigma_field_decl(self, field: Var, id: int) -> str:
        """sf stands for 'sigma field'."""
        return self.smt2_var_decl(field, f"sf{id}")

    def tau_field_decl(self, field: Var, id: int) -> str:
        """tf stands for 'tau field'."""
        return self.smt2_var_decl(field, f"tf{id}")

    def sigma_var_id(self, var: str, id: int) -> str:
        """sv stands for 'sigma variable'."""
        return self.smt2_var_id(var, f"sv{id}")

    def tau_var_id(self, var: str, id: int) -> str:
        """tv stands for 'tau variable'."""
        assert isinstance(var, str)
        assert var != "value"
        return self.smt2_var_id(var, f"tv{id}")

    def sigma_field_id(self, field: str, id: int) -> str:
        """sf stands for 'sigma field'."""
        return self.smt2_var_id(field, f"sf{id}")

    def tau_field_id(self, field: str, id: int) -> str:
        """tf stands for 'tau field'."""
        return self.smt2_var_id(field, f"tf{id}")

    def sigma_vars_decl(self, id: int) -> Iterable[str]:
        return (self.sigma_var_decl(var, id) for var in self.vars)

    def sigma_fields_decl(self, id: int) -> Iterable[str]:
        return (self.sigma_field_decl(field, id) for field in self.fields)

    def tau_vars_decl(self, id: int) -> Iterable[str]:
        return (self.tau_var_decl(var, id) for var in self.vars)

    def tau_fields_decl(self, id: int) -> Iterable[str]:
        return (self.tau_field_decl(field, id) for field in self.fields)

    def sigma_vars_id(self, id: int) -> Iterable[str]:
        return (self.sigma_var_id(var.name, id) for var in self.vars)

    def sigma_fields_id(self, id: int) -> Iterable[str]:
        return (self.sigma_field_id(field.name, id) for field in self.fields)

    def tau_vars_id(self, id: int) -> Iterable[str]:
        return (self.tau_var_id(var.name, id) for var in self.vars)

    def tau_fields_id(self, id: int) -> Iterable[str]:
        return (self.tau_field_id(field.name, id) for field in self.fields)

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
            case EnumConst(sort, value) if sort == BOOL:
                return smt2true() if value == TRUE else smt2false()
            case EnumConst():
                return smt2true()
            case _:
                raise RuntimeError(f"Unsupported expression type: {expr}")

    def declare_predicate(self, lab: Label):
        lab_id = self.labels.id(lab)
        pred_name = f"Lab{lab_id}"
        args_sorts = chain.from_iterable(
            chain(
                (SMT2FileBuilder.IR_TO_SMT2_SORT[var.sort] for var in self.vars),
                (SMT2FileBuilder.IR_TO_SMT2_SORT[field.sort] for field in self.fields),
            )
            for _ in reversed(lab)
        )
        decl = smt2decl(pred_name, args_sorts)
        self.decls.add(decl)

    def assert_internal_replaced_step(self, tau: Label, ancestor: Label, stmt: Instruction):
        self.declare_predicate(tau)
        constraints = []

        def iter_origins(label: Label) -> Iterable[Label]:
            current: Label | None = label
            while current is not None:
                yield current
                current = current.origin

        origins = tuple(reversed(tuple(iter_origins(tau))))
        assert len(origins) != 0
        ancestor_origins = tuple(reversed(tuple(iter_origins(ancestor))))

        variable_decls = list(
            chain.from_iterable(
                chain(self.tau_vars_decl(self.id(lab)), self.tau_fields_decl(self.id(lab))) for lab in origins
            )
        )
        variable_decls.extend(self.tau_vars_decl(self.id(ancestor)))
        variable_decls.extend(self.tau_fields_decl(self.id(ancestor)))
        tau_args = list(
            chain.from_iterable(
                chain(self.tau_vars_id(self.id(lab)), self.tau_fields_id(self.id(lab))) for lab in origins
            )
        )
        ancestor_args = list(
            chain.from_iterable(
                chain(self.tau_vars_id(self.id(lab)), self.tau_fields_id(self.id(lab))) for lab in ancestor_origins
            )
        )

        if any(isinstance(event, (OOM, ERR, LOF)) for event in tau.frame.events):
            pred = f"Lab{self.id(tau)}"
            query = smt2assert(smt2forall(variable_decls, smt2implies(smt2predicate(pred, tau_args), smt2false())))
            if OOM() in tau.frame.events:
                self.oom_queries.add(query)
            if ERR() in tau.frame.events:
                self.err_qeueries.add(query)
            if LOF() in tau.frame.events:
                self.lof_queries.add(query)

        def var_id_maker(v: str):
            return self.tau_var_id(v, self.id(ancestor))

        def field_id_maker(f: str):
            return self.tau_field_id(f, self.id(ancestor))

        match stmt:
            case IfGoto(cond, _) if not isinstance(cond, PtrIsPtr):
                cond = normalized_expr(cond, tau.frame)
                cond = Not(cond) if tau.frame.pc == ancestor.frame.pc + 1 else cond
                constraints = []
                if cond not in {TRUE, FALSE}:
                    cond_smt2 = self.expr_to_smt2(
                        cond,
                        var_id_maker,
                        field_id_maker,
                    )
                    constraints.append(cond_smt2)
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
            case VarAssignExpr(var, expr):
                expr = normalized_expr(expr, tau.frame)
                if not isinstance(expr, EnumConst) and not (isinstance(expr, (Field, Var)) and sort_of(expr).is_enum()):
                    if isinstance(expr, Field):
                        expr_smt2 = field_id_maker(expr.name)
                    else:
                        expr_smt2 = self.expr_to_smt2(expr, var_id_maker, field_id_maker)
                    constraints = [smt2equals(self.tau_var_id(var.name, self.id(tau)), expr_smt2)]
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    if left != self.tau_var_id(var.name, self.id(tau)):
                        constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
            case FieldAssignExpr(field, expr):
                expr = normalized_expr(expr, tau.frame)
                var: Var = field.ptr.sort.pointee.fields[field.name]  # type: ignore
                assert isinstance(var, Var)
                if not isinstance(expr, EnumConst):
                    expr_smt2 = self.expr_to_smt2(expr, var_id_maker, field_id_maker)
                    constraints = [smt2equals(self.tau_field_id(var.name, self.id(tau)), expr_smt2)]
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    if left != self.tau_field_id(var.name, self.id(tau)):
                        constraints.append(smt2equals(left, right))
            case _:
                constraints: list[str] = []
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
        pred_ancestor = f"Lab{self.id(ancestor)}"
        pred_tau = f"Lab{self.id(tau)}"
        clause = smt2assert(
            smt2forall(
                variable_decls,
                smt2implies(
                    smt2and(smt2predicate(pred_ancestor, ancestor_args), *constraints),
                    smt2predicate(pred_tau, tau_args),
                ),
            )
        )
        self.chcs.add(clause)

    def assert_internal_extended_step(self, tau: Label, ancestor: Label, stmt: Instruction):
        self.declare_predicate(tau)
        constraints = []
        ancestor = tau.origin
        assert ancestor is not None

        def iter_origins(label: Label) -> Iterable[Label]:
            current: Label | None = label
            while current is not None:
                yield current
                current = current.origin

        origins = tuple(reversed(tuple(iter_origins(tau))))

        variable_decls = list(
            chain.from_iterable(
                chain(self.tau_vars_decl(self.id(lab)), self.tau_fields_decl(self.id(lab))) for lab in origins
            )
        )
        tau_args = list(
            chain.from_iterable(
                chain(self.tau_vars_id(self.id(lab)), self.tau_fields_id(self.id(lab))) for lab in origins
            )
        )
        ancestor_args = list(
            chain.from_iterable(
                chain(self.tau_vars_id(self.id(lab)), self.tau_fields_id(self.id(lab))) for lab in origins[:-1]
            )
        )

        if any(isinstance(event, (OOM, ERR, LOF)) for event in tau.frame.events):
            pred = f"Lab{self.id(tau)}"
            query = smt2assert(smt2forall(variable_decls, smt2implies(smt2predicate(pred, tau_args), smt2false())))
            if OOM() in tau.frame.events:
                self.oom_queries.add(query)
            if ERR() in tau.frame.events:
                self.err_qeueries.add(query)
            if LOF() in tau.frame.events:
                self.lof_queries.add(query)

        def var_id_maker(v: str):
            return self.tau_var_id(v, self.id(ancestor))

        def field_id_maker(f: str):
            return self.tau_field_id(f, self.id(ancestor))

        match stmt:
            case IfGoto(cond, _) if not isinstance(cond, PtrIsPtr):
                cond = Not(cond) if tau.frame.pc == ancestor.frame.pc + 1 else cond
                cond = normalized_expr(cond, tau.frame)
                constraints = []
                if cond not in {TRUE, FALSE}:
                    cond_smt2 = self.expr_to_smt2(
                        cond,
                        var_id_maker,
                        field_id_maker,
                    )
                    constraints.append(cond_smt2)
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
            case VarAssignExpr(var, expr):
                expr = normalized_expr(expr, tau.frame)
                if not isinstance(expr, EnumConst) and not (isinstance(expr, (Field, Var)) and sort_of(expr).is_enum()):
                    if isinstance(expr, Field):
                        expr_smt2 = field_id_maker(expr.name)
                    else:
                        expr_smt2 = self.expr_to_smt2(expr, var_id_maker, field_id_maker)
                    constraints = [smt2equals(self.tau_var_id(var.name, self.id(tau)), expr_smt2)]
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    if left != self.tau_var_id(var.name, self.id(tau)):
                        constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
            case FieldAssignExpr(field, expr):
                expr = normalized_expr(expr, tau.frame)
                var: Var = field.ptr.sort.pointee.fields[field.name]  # type: ignore
                assert isinstance(var, Var)
                if not isinstance(expr, EnumConst):
                    expr_smt2 = self.expr_to_smt2(expr, var_id_maker, field_id_maker)
                    constraints = [smt2equals(self.tau_field_id(var.name, self.id(tau)), expr_smt2)]
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    if left != self.tau_field_id(var.name, self.id(tau)):
                        constraints.append(smt2equals(left, right))
            case _:
                constraints: list[str] = []
                for left, right in zip(self.tau_vars_id(self.id(tau)), self.tau_vars_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
                for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(ancestor))):
                    constraints.append(smt2equals(left, right))
        pred_ancestor = f"Lab{self.id(ancestor)}"
        pred_tau = f"Lab{self.id(tau)}"
        clause = smt2assert(
            smt2forall(
                variable_decls,
                smt2implies(
                    smt2and(smt2predicate(pred_ancestor, ancestor_args), *constraints),
                    smt2predicate(pred_tau, tau_args),
                ),
            )
        )
        self.chcs.add(clause)

    def assert_internal_step(self, lab: Label, ancestor: Label, stmt: Instruction):
        if lab.origin == ancestor:
            self.assert_internal_extended_step(lab, ancestor, stmt)
        else:
            self.assert_internal_replaced_step(lab, ancestor, stmt)

    def assert_external_step(self, pair: Pair):
        sigma = pair.follower()
        tau = pair.leader()
        self.declare_predicate(sigma)
        self.declare_predicate(tau)
        constraints: list[str] = []

        def iter_origins(label: Label) -> Iterable[Label]:
            current: Label | None = label
            while current is not None:
                yield current
                current = current.origin

        sigma_origins = tuple(reversed(tuple(iter_origins(sigma))))
        tau_origins = tuple(reversed(tuple(iter_origins(tau))))
        tau_ancestor = tau.origin
        # Build equality constraints between sigma and tau variables/fields according to the pair's direction
        for lab in sigma_origins[1:]:
            match lab.frame.prev:
                case dir, i if dir == pair.rev_dir():
                    for left, right in zip(self.sigma_vars_id(self.id(lab)), self.tau_vars_id(self.id(tau_origins[i]))):
                        constraints.append(smt2equals(left, right))
                    # for left, right in zip(self.sigma_fields_id(self.id(lab)), self.sigma_fields_id(lab.origin.id)):
                    #     constraints.append(smt2equals(left, right))
                case _:
                    continue

        for lab in tau_origins[1:]:
            match lab.frame.prev:
                case dir, i if dir == pair.dir():
                    for left, right in zip(
                        self.tau_vars_id(self.id(lab)), self.sigma_vars_id(self.id(sigma_origins[i]))
                    ):
                        constraints.append(smt2equals(left, right))
                    # for left, right in zip(self.tau_fields_id(self.id(lab)), self.tau_fields_id(lab.origin.id)):
                    #     constraints.append(smt2equals(left, right))
                case _:
                    continue

        for left, right in zip(self.tau_fields_id(self.id(tau)), self.tau_fields_id(self.id(tau_ancestor))):
            constraints.append(smt2equals(left, right))

        pred_ancestor = f"Lab{self.id(tau_ancestor)}"
        pred_sigma = f"Lab{self.id(sigma)}"
        pred_tau = f"Lab{self.id(tau)}"
        # Declarations for all sigma and tau variables/fields
        variable_decls = list(
            chain.from_iterable(
                chain(
                    (self.sigma_vars_decl(self.id(lab)) for lab in sigma_origins),
                    (self.sigma_fields_decl(self.id(lab)) for lab in sigma_origins),
                    (self.tau_vars_decl(self.id(lab)) for lab in tau_origins),
                    (self.tau_fields_decl(self.id(lab)) for lab in tau_origins),
                )
            )
        )
        # Predicate arguments (ids)
        sigma_args = list(
            chain.from_iterable(
                chain(self.sigma_vars_id(self.id(lab)), self.sigma_fields_id(self.id(lab))) for lab in sigma_origins
            )
        )
        tau_args = list(
            chain.from_iterable(
                chain(self.tau_vars_id(self.id(lab)), self.tau_fields_id(self.id(lab))) for lab in tau_origins
            )
        )
        ancestor_args = chain.from_iterable(
            chain(self.tau_vars_id(self.id(lab)), self.tau_fields_id(self.id(lab))) for lab in tau_origins[:-1]
        )
        # Build the SMT2 string
        clause = smt2assert(
            smt2forall(
                variable_decls,
                smt2implies(
                    smt2and(
                        smt2predicate(pred_ancestor, ancestor_args),
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
        pred = f"Lab{self.id(lab)}"
        variable_decls = chain.from_iterable(
            chain(self.tau_vars_decl(f.index), self.tau_fields_decl(f.index)) for f in reversed(lab)
        )
        args = chain.from_iterable(chain(self.tau_vars_id(f.index), self.tau_fields_id(f.index)) for f in reversed(lab))
        fact = smt2assert(smt2forall(variable_decls, smt2predicate(pred, args)))
        self.chcs.add(fact)

    def is_trivially_sat_for(self, exit_code: ExitCodeKind) -> bool:
        excode_to_queries = {
            ExitCodeKind.ERR: self.err_qeueries,
            ExitCodeKind.OOM: self.oom_queries,
            ExitCodeKind.LABEL_OVERFLOW: self.lof_queries,
        }
        return len(excode_to_queries[exit_code]) == 0

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
