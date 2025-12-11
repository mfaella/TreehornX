from chc.core import Label
from ir.expressions import FALSE, TRUE, And, EnumConst, Eq, Expr, Ne, Not, Or, PtrIsNil, PtrIsPtr, Var, sort_of
from ir.sorts import Sort


def ppexp(expr: Expr, lab: Label) -> Expr:  # noqa: PLR0915
    match expr:
        case Var(name, sort) if sort.is_enum():
            flag_name = lab[-1].enum_values[name]
            return EnumConst(sort, flag_name)  # type: ignore
        case Not(Not(e)):
            return ppexp(e, lab)
        case Not(e):
            if e == TRUE:
                return FALSE
            elif e == FALSE:
                return TRUE
            e = ppexp(e, lab)
            return ppexp(Not(e), lab)
        case And():
            new_args = [ppexp(arg, lab) for arg in expr.args()]
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
            new_args = [ppexp(arg, lab) for arg in expr.args()]
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
            lhs = ppexp(lhs, lab)
            rhs = ppexp(rhs, lab)
            if lhs == rhs:
                return TRUE
            elif sort_of(lhs).is_enum():
                assert isinstance(lhs, (Var, EnumConst))
                if isinstance(lhs, Var):
                    flag_name = lab[-1].enum_values[lhs.name]
                    lhs = EnumConst(sort_of(lhs), flag_name)  # type: ignore
                if isinstance(rhs, Var):
                    flag_name = lab[-1].enum_values[rhs.name]
                    rhs = EnumConst(sort_of(rhs), flag_name)  # type: ignore
                return TRUE if lhs == rhs else FALSE
            else:
                return Eq(lhs, rhs)
        case PtrIsNil(p):
            assert isinstance(p, Var)
            return TRUE if lab[-1].isnil[p.name] else FALSE
        case PtrIsPtr(_, _):
            raise NotImplementedError("PtrIsPtr not supported in ppexp")
        case Ne(lhs, rhs):
            lhs = ppexp(lhs, lab)
            rhs = ppexp(rhs, lab)
            if lhs == rhs:
                return FALSE
            elif sort_of(lhs).is_enum():
                assert isinstance(lhs, (Var, EnumConst))
                if isinstance(lhs, Var):
                    flag_name = lab[-1].enum_values[lhs.name]
                    lhs = EnumConst(sort_of(lhs), flag_name)  # type: ignore
                if isinstance(rhs, Var):
                    flag_name = lab[-1].enum_values[rhs.name]
                    rhs = EnumConst(sort_of(rhs), flag_name)  # type: ignore
                return FALSE if lhs == rhs else TRUE
            else:
                return Ne(lhs, rhs)
        case e:
            return e
