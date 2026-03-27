from typing import Iterable


def assert_(formula: str) -> str:
    return f"(assert {formula})"


def forall(variables_decls: Iterable[tuple[str, str]], formula: str) -> str:
    variables_decls = list(variables_decls)
    bounded_vars_names = set(name for name, _ in variables_decls)
    if len(bounded_vars_names) < len(variables_decls):
        raise ValueError("Duplicate variable names in forall quantifier.")
    var_decls_str = " ".join(f"({name} {sort})" for name, sort in variables_decls)
    return f"(forall ({var_decls_str}) {formula})"


def operator(op: str, args: Iterable[str]) -> str:
    return f"({op} {' '.join(args)})"


def equals(left: str, right: str) -> str:
    return operator("=", [left, right])


def not_equals(left: str, right: str) -> str:
    return not_(equals(left, right))


def lt(left: str, right: str) -> str:
    return operator("<", [left, right])


def gt(left: str, right: str) -> str:
    return operator(">", [left, right])


def le(left: str, right: str) -> str:
    return operator("<=", [left, right])


def ge(left: str, right: str) -> str:
    return operator(">=", [left, right])


def and_(*conjuncts: str) -> str:
    return operator("and", conjuncts)


def or_(*disjuncts: str) -> str:
    return operator("or", disjuncts)


def implies(antecedent: str, consequent: str) -> str:
    return operator("=>", [antecedent, consequent])


def not_(arg: str) -> str:
    return operator("not", [arg])


def plus(*args: str) -> str:
    return operator("+", args)


def minus(left: str, right: str) -> str:
    return operator("-", [left, right])


def times(*args: str) -> str:
    return operator("*", args)


def div(left: str, right: str) -> str:
    return operator("/", [left, right])


def predicate_application(pred_name: str, args: Iterable[str]) -> str:
    return f"({pred_name} {' '.join(args)})"


def decl_fun(pred_name: str, return_sort: str, args_sorts: Iterable[str]) -> str:
    return f"(declare-fun {pred_name} ({' '.join(args_sorts)}) {return_sort})"


def false() -> str:
    return "false"


def true() -> str:
    return "true"


def intType() -> str:  # noqa: N802
    return "Int"


def boolType() -> str:  # noqa: N802
    return "Bool"


def realType() -> str:  # noqa: N802
    return "Real"


def int_(value: int) -> str:
    return str(value)


def real_(value: float) -> str:
    return str(value)


def bool_(value: bool) -> str:
    return true() if value else false()
