"""Substitution and simplification of the terms of `sexpr`."""

from __future__ import annotations

from itertools import count
from typing import Callable, Iterator, Mapping, overload

from treehornx.chc.smt.sexpr import FALSE, TRUE, Application, Clause, Constant, Operator, OpExpr, SExpr, Type, Var


# ---------------------------------------------------------------------------
# substitution
# ---------------------------------------------------------------------------


@overload
def substitute(node: SExpr, mapping: Mapping[Var, SExpr]) -> SExpr: ...
@overload
def substitute(node: Application, mapping: Mapping[Var, SExpr]) -> Application: ...
@overload
def substitute(node: Clause, mapping: Mapping[Var, SExpr]) -> Clause: ...
def substitute(node: SExpr | Application | Clause, mapping: Mapping[Var, SExpr]) -> SExpr | Application | Clause:
    """`node` with every variable in `mapping` replaced, simultaneously. Unchanged subterms are shared."""
    match node:
        case Var():
            return mapping.get(node, node)
        case OpExpr(op, args):
            new_args = tuple(substitute(arg, mapping) for arg in args)
            return node if _same(args, new_args) else OpExpr(op, *new_args)
        case Application(predicate, args):
            new_args = tuple(substitute(arg, mapping) for arg in args)
            return node if _same(args, new_args) else Application(predicate, *new_args)
        case Clause(head, body):
            new_head = head if head is False else substitute(head, mapping)
            new_body = tuple(substitute(b, mapping) for b in body)
            if new_head is head and _same(body, new_body):
                return node
            return Clause(new_head, *new_body)
        case _:
            return node


def _same(old: tuple[object, ...], new: tuple[object, ...]) -> bool:
    return all(a is b for a, b in zip(old, new))


# ---------------------------------------------------------------------------
# fresh variables
# ---------------------------------------------------------------------------

_fresh_ids = count()


def fresh_var(type: Type, prefix: str = "e") -> Var:
    """A variable named `<prefix><n>`, with n unique in the process."""
    return Var(f"{prefix}{next(_fresh_ids)}", type)


# ---------------------------------------------------------------------------
# simplification
# ---------------------------------------------------------------------------


def conjuncts(expr: SExpr) -> Iterator[SExpr]:
    """The top-level conjuncts of `expr`, nested conjunctions flattened."""
    if isinstance(expr, OpExpr) and expr.op is Operator.AND:
        for arg in expr.args:
            yield from conjuncts(arg)
    else:
        yield expr


def _bool(expr: SExpr) -> bool | None:
    """The value of a Bool constant, None for any other term."""
    if isinstance(expr, Constant) and isinstance(expr.value, bool):
        return expr.value
    return None


def _int(expr: SExpr) -> int | None:
    """The value of an Int constant, None for any other term."""
    if isinstance(expr, Constant) and not isinstance(expr.value, bool):
        return expr.value
    return None


def simplify(expr: SExpr) -> SExpr:
    """A bottom-up pass of constant folding and Boolean normalisation, preserving equivalence."""
    if not isinstance(expr, OpExpr):
        return expr
    args = tuple(simplify(arg) for arg in expr.args)
    match expr.op:
        case Operator.AND | Operator.OR:
            return _simplify_junction(expr.op, args)
        case Operator.NOT:
            return _simplify_not(args[0])
        case Operator.IMPLIES:
            return _simplify_implies(args[0], args[1])
        case Operator.ITE:
            return _simplify_ite(args[0], args[1], args[2])
        case Operator.EQ:
            return _simplify_eq(args[0], args[1])
        case Operator.LT | Operator.LE | Operator.GT | Operator.GE:
            return _simplify_comparison(expr.op, args[0], args[1])
        case Operator.ADD | Operator.MUL:
            return _simplify_sum_product(expr.op, args)
        case Operator.SUB:
            return _simplify_sub(args)
        case Operator.DIV | Operator.MOD:
            # folding them would need the SMT-LIB semantics of negative operands, left as they are
            return OpExpr(expr.op, *args)


def _simplify_junction(op: Operator, args: tuple[SExpr, ...]) -> SExpr:
    neutral = op is Operator.AND  # true for and, false for or
    flat: dict[SExpr, None] = {}  # ordered set: duplicates are dropped, the first occurrence is kept
    for arg in args:
        nested = arg.args if isinstance(arg, OpExpr) and arg.op is op else (arg,)
        for a in nested:
            value = _bool(a)
            if value is None:
                flat[a] = None
            elif value != neutral:
                return Constant(not neutral)
    if not flat:
        return Constant(neutral)
    if len(flat) == 1:
        return next(iter(flat))
    return OpExpr(op, *flat)


def _simplify_not(arg: SExpr) -> SExpr:
    value = _bool(arg)
    if value is not None:
        return Constant(not value)
    if isinstance(arg, OpExpr) and arg.op is Operator.NOT:
        return arg.args[0]
    return OpExpr(Operator.NOT, arg)


def _simplify_implies(left: SExpr, right: SExpr) -> SExpr:
    lv, rv = _bool(left), _bool(right)
    if lv is False or rv is True:
        return TRUE
    if lv is True:
        return right
    if rv is False:
        return _simplify_not(left)
    if left == right:
        return TRUE
    return OpExpr(Operator.IMPLIES, left, right)


def _simplify_ite(cond: SExpr, then: SExpr, other: SExpr) -> SExpr:
    value = _bool(cond)
    if value is not None:
        return then if value else other
    if then == other:
        return then
    return OpExpr(Operator.ITE, cond, then, other)


def _simplify_eq(left: SExpr, right: SExpr) -> SExpr:
    if left == right:
        return TRUE
    if isinstance(left, Constant) and isinstance(right, Constant):
        return FALSE  # distinct constants of the same type
    # a = true is a, a = false is ¬a
    lv, rv = _bool(left), _bool(right)
    if lv is not None:
        return right if lv else _simplify_not(right)
    if rv is not None:
        return left if rv else _simplify_not(left)
    return OpExpr(Operator.EQ, left, right)


_COMPARISONS: dict[Operator, Callable[[int, int], bool]] = {
    Operator.LT: lambda a, b: a < b,
    Operator.LE: lambda a, b: a <= b,
    Operator.GT: lambda a, b: a > b,
    Operator.GE: lambda a, b: a >= b,
}


def _simplify_comparison(op: Operator, left: SExpr, right: SExpr) -> SExpr:
    lv, rv = _int(left), _int(right)
    if lv is not None and rv is not None:
        return Constant(_COMPARISONS[op](lv, rv))
    if left == right:
        return Constant(op in (Operator.LE, Operator.GE))
    return OpExpr(op, left, right)


def _simplify_sum_product(op: Operator, args: tuple[SExpr, ...]) -> SExpr:
    """+ and *: nested applications are flattened, constants are folded into one, placed last."""
    unit = 0 if op is Operator.ADD else 1
    folded = unit
    terms: list[SExpr] = []
    for arg in args:
        for a in arg.args if isinstance(arg, OpExpr) and arg.op is op else (arg,):
            value = _int(a)
            if value is None:
                terms.append(a)
            elif op is Operator.ADD:
                folded += value
            else:
                folded *= value
    if op is Operator.MUL and folded == 0:
        return Constant(0)
    if folded != unit or not terms:
        terms.append(Constant(folded))
    if len(terms) == 1:
        return terms[0]
    return OpExpr(op, *terms)


def _simplify_sub(args: tuple[SExpr, ...]) -> SExpr:
    if len(args) == 1:  # unary minus
        value = _int(args[0])
        return Constant(-value) if value is not None else OpExpr(Operator.SUB, *args)
    left, right = args[0], args[1:]
    values = [_int(a) for a in args]
    if all(v is not None for v in values):
        result = values[0]
        assert result is not None
        for v in values[1:]:
            assert v is not None
            result -= v
        return Constant(result)
    if len(right) == 1 and left == right[0]:
        return Constant(0)
    if len(right) == 1 and _int(right[0]) == 0:
        return left
    return OpExpr(Operator.SUB, *args)


def simplify_application(app: Application) -> Application:
    """`app` with its arguments simplified."""
    new_args = tuple(simplify(arg) for arg in app.args)
    return app if _same(app.args, new_args) else Application(app.predicate, *new_args)


def simplify_clause(clause: Clause) -> Clause:
    """`clause` with the constraints of the body and the arguments of every application simplified.

    The constraints are flattened into separate conjuncts and true conjuncts are dropped."""
    head = clause.head if clause.head is False else simplify_application(clause.head)
    body: list[SExpr | Application] = []
    for b in clause.body:
        if isinstance(b, Application):
            body.append(simplify_application(b))
        else:
            body.extend(c for c in conjuncts(simplify(b)) if _bool(c) is not True)
    return Clause(head, *body)
