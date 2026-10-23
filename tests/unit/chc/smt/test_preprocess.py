import pytest

from treehornx.chc.smt import sexpr as sx
from treehornx.chc.smt.preprocess import (
    conjuncts,
    fresh_var,
    simplify,
    simplify_application,
    simplify_clause,
    substitute,
)


X = sx.Var("x", sx.Type.Int)
Y = sx.Var("y", sx.Type.Int)
Z = sx.Var("z", sx.Type.Int)
A = sx.Var("a", sx.Type.Bool)
B = sx.Var("b", sx.Type.Bool)
P = sx.Predicate("P", [sx.Type.Int, sx.Type.Int])


def test_substitute_is_simultaneous() -> None:
    swapped = substitute(sx.OpExpr(sx.Operator.SUB, X, Y), {X: Y, Y: X})
    assert swapped == sx.OpExpr(sx.Operator.SUB, Y, X)


def test_substitute_shares_unchanged_terms() -> None:
    term = sx.OpExpr(sx.Operator.AND, sx.OpExpr(sx.Operator.GT, X, 0), A)
    assert substitute(term, {Y: Z}) is term
    app = sx.Application(P, X, Y)
    assert substitute(app, {Z: X}) is app
    clause = sx.Clause(sx.Application(P, X, Y), sx.OpExpr(sx.Operator.GT, X, 0))
    assert substitute(clause, {Z: X}) is clause
    assert substitute(sx.Constant(1), {X: Y}) == sx.Constant(1)


def test_substitute_clause() -> None:
    clause = sx.Clause(sx.Application(P, X, Y), sx.Application(P, Y, X), sx.OpExpr(sx.Operator.GT, X, 0))
    assert substitute(clause, {X: Z}) == sx.Clause(
        sx.Application(P, Z, Y), sx.Application(P, Y, Z), sx.OpExpr(sx.Operator.GT, Z, 0)
    )
    query = sx.Clause(False, sx.Application(P, X, X))
    assert substitute(query, {X: Y}) == sx.Clause(False, sx.Application(P, Y, Y))


def test_fresh_vars_are_distinct() -> None:
    first, second = fresh_var(sx.Type.Int), fresh_var(sx.Type.Bool, "k")
    assert first != second and first.name.startswith("e") and second.name.startswith("k")
    assert second.type is sx.Type.Bool


def test_conjuncts_flatten_nested_ands() -> None:
    assert list(
        conjuncts(sx.OpExpr(sx.Operator.AND, A, sx.OpExpr(sx.Operator.AND, B, sx.OpExpr(sx.Operator.GT, X, 0))))
    ) == [A, B, sx.OpExpr(sx.Operator.GT, X, 0)]
    assert list(conjuncts(sx.OpExpr(sx.Operator.OR, A, B))) == [sx.OpExpr(sx.Operator.OR, A, B)]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        # and / or
        (sx.OpExpr(sx.Operator.AND, A, sx.TRUE), A),
        (sx.OpExpr(sx.Operator.AND, A, sx.FALSE), sx.FALSE),
        (sx.OpExpr(sx.Operator.AND, A, sx.OpExpr(sx.Operator.AND, B, A)), sx.OpExpr(sx.Operator.AND, A, B)),
        (sx.OpExpr(sx.Operator.AND, sx.TRUE, sx.TRUE), sx.TRUE),
        (sx.OpExpr(sx.Operator.OR, A, sx.TRUE), sx.TRUE),
        (sx.OpExpr(sx.Operator.OR, A, sx.FALSE), A),
        (sx.OpExpr(sx.Operator.OR, sx.OpExpr(sx.Operator.OR, A, B), B), sx.OpExpr(sx.Operator.OR, A, B)),
        (sx.OpExpr(sx.Operator.OR, sx.FALSE, sx.FALSE), sx.FALSE),
        # not
        (sx.OpExpr(sx.Operator.NOT, sx.TRUE), sx.FALSE),
        (sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.NOT, A)), A),
        (sx.OpExpr(sx.Operator.NOT, A), sx.OpExpr(sx.Operator.NOT, A)),
        # implies
        (sx.OpExpr(sx.Operator.IMPLIES, sx.FALSE, A), sx.TRUE),
        (sx.OpExpr(sx.Operator.IMPLIES, A, sx.TRUE), sx.TRUE),
        (sx.OpExpr(sx.Operator.IMPLIES, sx.TRUE, A), A),
        (sx.OpExpr(sx.Operator.IMPLIES, A, sx.FALSE), sx.OpExpr(sx.Operator.NOT, A)),
        (sx.OpExpr(sx.Operator.IMPLIES, A, A), sx.TRUE),
        (sx.OpExpr(sx.Operator.IMPLIES, A, B), sx.OpExpr(sx.Operator.IMPLIES, A, B)),
        # ite
        (sx.OpExpr(sx.Operator.ITE, sx.TRUE, X, Y), X),
        (sx.OpExpr(sx.Operator.ITE, sx.FALSE, X, Y), Y),
        (sx.OpExpr(sx.Operator.ITE, A, X, X), X),
        (sx.OpExpr(sx.Operator.ITE, A, X, Y), sx.OpExpr(sx.Operator.ITE, A, X, Y)),
        # equality
        (sx.OpExpr(sx.Operator.EQ, X, X), sx.TRUE),
        (sx.OpExpr(sx.Operator.EQ, 1, 2), sx.FALSE),
        (sx.OpExpr(sx.Operator.EQ, sx.OpExpr(sx.Operator.ADD, 1, 1), 2), sx.TRUE),
        (sx.OpExpr(sx.Operator.EQ, A, True), A),
        (sx.OpExpr(sx.Operator.EQ, False, A), sx.OpExpr(sx.Operator.NOT, A)),
        (sx.OpExpr(sx.Operator.EQ, True, A), A),
        (sx.OpExpr(sx.Operator.EQ, A, False), sx.OpExpr(sx.Operator.NOT, A)),
        (sx.OpExpr(sx.Operator.EQ, X, Y), sx.OpExpr(sx.Operator.EQ, X, Y)),
        # comparisons
        (sx.OpExpr(sx.Operator.LT, 1, 2), sx.TRUE),
        (sx.OpExpr(sx.Operator.GE, 1, 2), sx.FALSE),
        (sx.OpExpr(sx.Operator.LE, X, X), sx.TRUE),
        (sx.OpExpr(sx.Operator.GT, X, X), sx.FALSE),
        (sx.OpExpr(sx.Operator.LT, X, Y), sx.OpExpr(sx.Operator.LT, X, Y)),
        # arithmetic
        (sx.OpExpr(sx.Operator.ADD, X, 0), X),
        (sx.OpExpr(sx.Operator.ADD, 1, X, 2), sx.OpExpr(sx.Operator.ADD, X, 3)),
        (sx.OpExpr(sx.Operator.ADD, sx.OpExpr(sx.Operator.ADD, X, 1), Y), sx.OpExpr(sx.Operator.ADD, X, Y, 1)),
        (sx.OpExpr(sx.Operator.ADD, 1, 2), sx.Constant(3)),
        (sx.OpExpr(sx.Operator.MUL, X, 1), X),
        (sx.OpExpr(sx.Operator.MUL, X, 0), sx.Constant(0)),
        (sx.OpExpr(sx.Operator.MUL, 2, X, 3), sx.OpExpr(sx.Operator.MUL, X, 6)),
        (sx.OpExpr(sx.Operator.SUB, 5, 3), sx.Constant(2)),
        (sx.OpExpr(sx.Operator.SUB, X, X), sx.Constant(0)),
        (sx.OpExpr(sx.Operator.SUB, X, 0), X),
        (sx.OpExpr(sx.Operator.SUB, X, Y), sx.OpExpr(sx.Operator.SUB, X, Y)),
        (sx.OpExpr(sx.Operator.SUB, 4), sx.Constant(-4)),
        (sx.OpExpr(sx.Operator.SUB, X), sx.OpExpr(sx.Operator.SUB, X)),
        (sx.OpExpr(sx.Operator.DIV, sx.OpExpr(sx.Operator.ADD, X, 0), 2), sx.OpExpr(sx.Operator.DIV, X, 2)),
        (sx.OpExpr(sx.Operator.MOD, 4, 2), sx.OpExpr(sx.Operator.MOD, 4, 2)),
        # leaves
        (X, X),
        (sx.TRUE, sx.TRUE),
    ],
)
def test_simplify(term: sx.SExpr, expected: sx.SExpr) -> None:
    assert simplify(term) == expected


def test_simplify_application() -> None:
    app = sx.Application(P, sx.OpExpr(sx.Operator.ADD, X, 0), Y)
    assert simplify_application(app) == sx.Application(P, X, Y)
    unchanged = sx.Application(P, X, Y)
    assert simplify_application(unchanged) is unchanged


def test_simplify_clause_splits_and_drops_true() -> None:
    clause = sx.Clause(
        sx.Application(P, sx.OpExpr(sx.Operator.ADD, X, 0), Y),
        sx.Application(P, Y, sx.OpExpr(sx.Operator.MUL, X, 1)),
        sx.OpExpr(sx.Operator.AND, sx.OpExpr(sx.Operator.GT, X, 0), sx.OpExpr(sx.Operator.EQ, Y, Y)),
        sx.OpExpr(sx.Operator.EQ, Z, Z),
    )
    assert simplify_clause(clause) == sx.Clause(
        sx.Application(P, X, Y), sx.Application(P, Y, X), sx.OpExpr(sx.Operator.GT, X, 0)
    )
    query = sx.Clause(False, sx.Application(P, X, Y), sx.OpExpr(sx.Operator.LT, 1, 0))
    assert simplify_clause(query) == sx.Clause(False, sx.Application(P, X, Y), sx.FALSE)
