from treehornx.enum_labels.core.Label import Label
from treehornx.enum_labels.helpers import are_equal_after_rewind
from treehornx.ir.expressions import (
    FALSE,
    TRUE,
    And,
    EnumConst,
    Eq,
    Expr,
    Ge,
    Gt,
    Le,
    Lt,
    Ne,
    Not,
    Or,
    PtrIsNil,
    PtrIsPtr,
    Var,
    sort_of,
)


def normalized_expr(expr: Expr, lab_prev: Label) -> Expr:  # noqa: PLR0915
    f_prev = lab_prev.frame
    match expr:
        case Var(name, sort) if sort.is_enum():
            flag_name = f_prev.enum_vars[name]
            return EnumConst(sort, flag_name)  # type: ignore
        case Not(Not(e)):
            return normalized_expr(e, lab_prev)
        case Not(Eq(lhs, rhs)):
            return normalized_expr(Ne(lhs, rhs), lab_prev)
        case Not(Ne(lhs, rhs)):
            return normalized_expr(Eq(lhs, rhs), lab_prev)
        case Not(Le(lhs, rhs)):
            return normalized_expr(Gt(lhs, rhs), lab_prev)
        case Not(Lt(lhs, rhs)):
            return normalized_expr(Ge(lhs, rhs), lab_prev)
        case Not(Ge(lhs, rhs)):
            return normalized_expr(Lt(lhs, rhs), lab_prev)
        case Not(Gt(lhs, rhs)):
            return normalized_expr(Le(lhs, rhs), lab_prev)
        case Not(e):
            if e == TRUE:
                return FALSE
            elif e == FALSE:
                return TRUE
            normal_expr = normalized_expr(e, lab_prev)
            if e == normal_expr:
                return Not(normal_expr)
            else:
                return normalized_expr(Not(normal_expr), lab_prev)
        case And():
            new_args = [normalized_expr(arg, lab_prev) for arg in expr.args()]
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
            new_args = [normalized_expr(arg, lab_prev) for arg in expr.args()]
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
            lhs = normalized_expr(lhs, lab_prev)
            rhs = normalized_expr(rhs, lab_prev)
            if lhs == rhs:
                return TRUE
            elif sort_of(lhs).is_enum():
                assert isinstance(lhs, (Var, EnumConst))
                if isinstance(lhs, Var):
                    flag_name = f_prev.enum_vars[lhs.name]
                    lhs = EnumConst(sort_of(lhs), flag_name)  # type: ignore
                if isinstance(rhs, Var):
                    flag_name = f_prev.enum_vars[rhs.name]
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
            elif are_equal_after_rewind(lab_prev, p.name, q.name):
                return TRUE
            else:
                return FALSE

        case Ne(lhs, rhs):
            lhs = normalized_expr(lhs, lab_prev)
            rhs = normalized_expr(rhs, lab_prev)
            if lhs == rhs:
                return FALSE
            elif sort_of(lhs).is_enum():
                assert isinstance(lhs, (Var, EnumConst))
                if isinstance(lhs, Var):
                    flag_name = f_prev.enum_vars[lhs.name]
                    lhs = EnumConst(sort_of(lhs), flag_name)  # type: ignore
                if isinstance(rhs, Var):
                    flag_name = f_prev.enum_vars[rhs.name]
                    rhs = EnumConst(sort_of(rhs), flag_name)  # type: ignore
                return FALSE if lhs == rhs else TRUE
            else:
                return Ne(lhs, rhs)
        case e:
            return e
