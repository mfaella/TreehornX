from treehornx.ir.expressions import (
    FALSE,
    TRUE,
    And,
    EnumConst,
    Eq,
    Expr,
    Ne,
    Not,
    Or,
    PtrIsNil,
    PtrIsPtr,
    Var,
    sort_of,
)
from treehornx.ir.sorts import Sort

from .core import Frame


def ppexp(expr: Expr, f_prev: Frame) -> Expr:  # noqa: PLR0915
    match expr:
        case Var(name, sort) if sort.is_enum():
            flag_name = f_prev.enum_values[name]
            return EnumConst(sort, flag_name)  # type: ignore
        case Not(Not(e)):
            return ppexp(e, f_prev)
        case Not(e):
            if e == TRUE:
                return FALSE
            elif e == FALSE:
                return TRUE
            ppe = ppexp(e, f_prev)
            if e == ppe:
                return Not(ppe)
            else:
                return ppexp(Not(ppe), f_prev)
        case And():
            new_args = [ppexp(arg, f_prev) for arg in expr.args()]
            if FALSE in new_args:
                return FALSE
            new_args = [arg for arg in new_args if arg != TRUE]
            if not new_args:
                return TRUE
            elif len(new_args) == 1:
                return new_args[0]
            else:
                return And(*new_args)
        case Or():
            new_args = [ppexp(arg, f_prev) for arg in expr.args()]
            if TRUE in new_args:
                return TRUE
            new_args = [arg for arg in new_args if arg != FALSE]
            if not new_args:
                return FALSE
            elif len(new_args) == 1:
                return new_args[0]
            else:
                return Or(*new_args)
        case Eq(lhs, rhs):
            lhs = ppexp(lhs, f_prev)
            rhs = ppexp(rhs, f_prev)
            if lhs == rhs:
                return TRUE
            elif sort_of(lhs).is_enum():
                assert isinstance(lhs, (Var, EnumConst))
                if isinstance(lhs, Var):
                    flag_name = f_prev.enum_values[lhs.name]
                    lhs = EnumConst(sort_of(lhs), flag_name)  # type: ignore
                if isinstance(rhs, Var):
                    flag_name = f_prev.enum_values[rhs.name]
                    rhs = EnumConst(sort_of(rhs), flag_name)  # type: ignore
                return TRUE if lhs == rhs else FALSE
            else:
                return Eq(lhs, rhs)
        case PtrIsNil(p):
            assert isinstance(p, Var)
            return TRUE if f_prev.isnil[p.name] else FALSE
        case PtrIsPtr(p, q):
            assert isinstance(p, Var)
            assert isinstance(q, Var)
            if f_prev.isnil[p.name] != f_prev.isnil[q.name]:
                return FALSE
            elif f_prev.isnil[p.name]:
                return TRUE
            else:
                return expr

        case Ne(lhs, rhs):
            lhs = ppexp(lhs, f_prev)
            rhs = ppexp(rhs, f_prev)
            if lhs == rhs:
                return FALSE
            elif sort_of(lhs).is_enum():
                assert isinstance(lhs, (Var, EnumConst))
                if isinstance(lhs, Var):
                    flag_name = f_prev.enum_values[lhs.name]
                    lhs = EnumConst(sort_of(lhs), flag_name)  # type: ignore
                if isinstance(rhs, Var):
                    flag_name = f_prev.enum_values[rhs.name]
                    rhs = EnumConst(sort_of(rhs), flag_name)  # type: ignore
                return FALSE if lhs == rhs else TRUE
            else:
                return Ne(lhs, rhs)
        case e:
            return e
