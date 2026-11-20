import pytest

from treehornx import smt as sx
from treehornx.smt.preprocess import (
    conjuncts,
    fresh_var,
    make_non_trivial,
    simplify,
    simplify_application,
    simplify_clause,
    substitute,
)
from treehornx.smt.sexpr import Application, Clause, Predicate


X = sx.Var.make(name="x", type=sx.Type.Int)
Y = sx.Var.make(name="y", type=sx.Type.Int)
Z = sx.Var.make(name="z", type=sx.Type.Int)
A = sx.Var.make(name="a", type=sx.Type.Bool)
B = sx.Var.make(name="b", type=sx.Type.Bool)
P = Predicate.make(name="P", types=[sx.Type.Int, sx.Type.Int])


def test_substitute_is_simultaneous() -> None:
    swapped = substitute(sx.OpExpr.make(op=sx.Operator.SUB, args=(X, Y)), {X: Y, Y: X})
    assert swapped == sx.OpExpr.make(op=sx.Operator.SUB, args=(Y, X))


def test_substitute_shares_unchanged_terms() -> None:
    term = sx.OpExpr.make(op=sx.Operator.AND, args=(sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0)), A))
    assert substitute(term, {Y: Z}) is term
    app = Application.make(predicate=P, args=(X, Y))
    assert substitute(app, {Z: X}) is app
    clause = Clause.make(
        head=Application.make(predicate=P, args=(X, Y)), body=(sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0)),)
    )
    assert substitute(clause, {Z: X}) is clause
    assert substitute(sx.Constant.make(value=1), {X: Y}) == sx.Constant.make(value=1)


def test_substitute_clause() -> None:
    clause = Clause.make(
        head=Application.make(predicate=P, args=(X, Y)),
        body=(Application.make(predicate=P, args=(Y, X)), sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0))),
    )
    assert substitute(clause, {X: Z}) == Clause.make(
        head=Application.make(predicate=P, args=(Z, Y)),
        body=(Application.make(predicate=P, args=(Y, Z)), sx.OpExpr.make(op=sx.Operator.GT, args=(Z, 0))),
    )
    query = Clause.make(head=False, body=(Application.make(predicate=P, args=(X, X)),))
    assert substitute(query, {X: Y}) == Clause.make(head=False, body=(Application.make(predicate=P, args=(Y, Y)),))


def test_fresh_vars_are_distinct() -> None:
    first, second = fresh_var(sx.Type.Int), fresh_var(sx.Type.Bool, "k")
    assert first != second and first.name.startswith("e") and second.name.startswith("k")
    assert second.type is sx.Type.Bool


def test_conjuncts_flatten_nested_ands() -> None:
    assert list(
        conjuncts(
            sx.OpExpr.make(
                op=sx.Operator.AND,
                args=(A, sx.OpExpr.make(op=sx.Operator.AND, args=(B, sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0))))),
            )
        )
    ) == [A, B, sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0))]
    assert list(conjuncts(sx.OpExpr.make(op=sx.Operator.OR, args=(A, B)))) == [
        sx.OpExpr.make(op=sx.Operator.OR, args=(A, B))
    ]


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        # and / or
        (sx.OpExpr.make(op=sx.Operator.AND, args=(A, sx.TRUE)), A),
        (sx.OpExpr.make(op=sx.Operator.AND, args=(A, sx.FALSE)), sx.FALSE),
        (
            sx.OpExpr.make(op=sx.Operator.AND, args=(A, sx.OpExpr.make(op=sx.Operator.AND, args=(B, A)))),
            sx.OpExpr.make(op=sx.Operator.AND, args=(A, B)),
        ),
        (sx.OpExpr.make(op=sx.Operator.AND, args=(sx.TRUE, sx.TRUE)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.OR, args=(A, sx.TRUE)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.OR, args=(A, sx.FALSE)), A),
        (
            sx.OpExpr.make(op=sx.Operator.OR, args=(sx.OpExpr.make(op=sx.Operator.OR, args=(A, B)), B)),
            sx.OpExpr.make(op=sx.Operator.OR, args=(A, B)),
        ),
        (sx.OpExpr.make(op=sx.Operator.OR, args=(sx.FALSE, sx.FALSE)), sx.FALSE),
        # not
        (sx.OpExpr.make(op=sx.Operator.NOT, args=(sx.TRUE,)), sx.FALSE),
        (sx.OpExpr.make(op=sx.Operator.NOT, args=(sx.OpExpr.make(op=sx.Operator.NOT, args=(A,)),)), A),
        (sx.OpExpr.make(op=sx.Operator.NOT, args=(A,)), sx.OpExpr.make(op=sx.Operator.NOT, args=(A,))),
        # implies
        (sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(sx.FALSE, A)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(A, sx.TRUE)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(sx.TRUE, A)), A),
        (sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(A, sx.FALSE)), sx.OpExpr.make(op=sx.Operator.NOT, args=(A,))),
        (sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(A, A)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(A, B)), sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(A, B))),
        # ite
        (sx.OpExpr.make(op=sx.Operator.ITE, args=(sx.TRUE, X, Y)), X),
        (sx.OpExpr.make(op=sx.Operator.ITE, args=(sx.FALSE, X, Y)), Y),
        (sx.OpExpr.make(op=sx.Operator.ITE, args=(A, X, X)), X),
        (sx.OpExpr.make(op=sx.Operator.ITE, args=(A, X, Y)), sx.OpExpr.make(op=sx.Operator.ITE, args=(A, X, Y))),
        # equality
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(X, X)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(1, 2)), sx.FALSE),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(sx.OpExpr.make(op=sx.Operator.ADD, args=(1, 1)), 2)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(A, True)), A),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(False, A)), sx.OpExpr.make(op=sx.Operator.NOT, args=(A,))),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(True, A)), A),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(A, False)), sx.OpExpr.make(op=sx.Operator.NOT, args=(A,))),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(X, Y)), sx.OpExpr.make(op=sx.Operator.EQ, args=(X, Y))),
        # comparisons
        (sx.OpExpr.make(op=sx.Operator.LT, args=(1, 2)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.GE, args=(1, 2)), sx.FALSE),
        (sx.OpExpr.make(op=sx.Operator.LE, args=(X, X)), sx.TRUE),
        (sx.OpExpr.make(op=sx.Operator.GT, args=(X, X)), sx.FALSE),
        (sx.OpExpr.make(op=sx.Operator.LT, args=(X, Y)), sx.OpExpr.make(op=sx.Operator.LT, args=(X, Y))),
        # arithmetic
        (sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 0)), X),
        (sx.OpExpr.make(op=sx.Operator.ADD, args=(1, X, 2)), sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 3))),
        (
            sx.OpExpr.make(op=sx.Operator.ADD, args=(sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 1)), Y)),
            sx.OpExpr.make(op=sx.Operator.ADD, args=(X, Y, 1)),
        ),
        (sx.OpExpr.make(op=sx.Operator.ADD, args=(1, 2)), sx.Constant.make(value=3)),
        (sx.OpExpr.make(op=sx.Operator.MUL, args=(X, 1)), X),
        (sx.OpExpr.make(op=sx.Operator.MUL, args=(X, 0)), sx.Constant.make(value=0)),
        (sx.OpExpr.make(op=sx.Operator.MUL, args=(2, X, 3)), sx.OpExpr.make(op=sx.Operator.MUL, args=(X, 6))),
        (sx.OpExpr.make(op=sx.Operator.SUB, args=(5, 3)), sx.Constant.make(value=2)),
        (sx.OpExpr.make(op=sx.Operator.SUB, args=(X, X)), sx.Constant.make(value=0)),
        (sx.OpExpr.make(op=sx.Operator.SUB, args=(X, 0)), X),
        (sx.OpExpr.make(op=sx.Operator.SUB, args=(X, Y)), sx.OpExpr.make(op=sx.Operator.SUB, args=(X, Y))),
        (sx.OpExpr.make(op=sx.Operator.SUB, args=(4,)), sx.Constant.make(value=-4)),
        (sx.OpExpr.make(op=sx.Operator.SUB, args=(X,)), sx.OpExpr.make(op=sx.Operator.SUB, args=(X,))),
        (
            sx.OpExpr.make(op=sx.Operator.DIV, args=(sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 0)), 2)),
            sx.OpExpr.make(op=sx.Operator.DIV, args=(X, 2)),
        ),
        (sx.OpExpr.make(op=sx.Operator.MOD, args=(4, 2)), sx.OpExpr.make(op=sx.Operator.MOD, args=(4, 2))),
        # leaves
        (X, X),
        (sx.TRUE, sx.TRUE),
    ],
)
def test_simplify(term: sx.SExpr, expected: sx.SExpr) -> None:
    assert simplify(term) == expected


def test_simplify_application() -> None:
    app = Application.make(predicate=P, args=(sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 0)), Y))
    assert simplify_application(app) == Application.make(predicate=P, args=(X, Y))
    unchanged = Application.make(predicate=P, args=(X, Y))
    assert simplify_application(unchanged) is unchanged


def test_simplify_clause_splits_and_drops_true() -> None:
    clause = Clause.make(
        head=Application.make(predicate=P, args=(sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 0)), Y)),
        body=(
            Application.make(predicate=P, args=(Y, sx.OpExpr.make(op=sx.Operator.MUL, args=(X, 1)))),
            sx.OpExpr.make(
                op=sx.Operator.AND,
                args=(sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0)), sx.OpExpr.make(op=sx.Operator.EQ, args=(Y, Y))),
            ),
            sx.OpExpr.make(op=sx.Operator.EQ, args=(Z, Z)),
        ),
    )
    assert simplify_clause(clause) == Clause.make(
        head=Application.make(predicate=P, args=(X, Y)),
        body=(Application.make(predicate=P, args=(Y, X)), sx.OpExpr.make(op=sx.Operator.GT, args=(X, 0))),
    )
    query = Clause.make(
        head=False, body=(Application.make(predicate=P, args=(X, Y)), sx.OpExpr.make(op=sx.Operator.LT, args=(1, 0)))
    )
    assert simplify_clause(query) == Clause.make(
        head=False, body=(Application.make(predicate=P, args=(X, Y)), sx.FALSE)
    )


def test_make_non_trivial() -> None:
    eq = sx.OpExpr.make(op=sx.Operator.EQ, args=(X, Y))
    trivial = sx.OpExpr.make(op=sx.Operator.EQ, args=(X, X))
    folded = sx.OpExpr.make(op=sx.Operator.EQ, args=(Z, sx.OpExpr.make(op=sx.Operator.ADD, args=(1, 2))))
    both = sx.OpExpr.make(op=sx.Operator.AND, args=(eq, A))
    assert make_non_trivial([trivial, both, folded]) == [eq, A, sx.OpExpr.make(op=sx.Operator.EQ, args=(Z, 3))]
    assert make_non_trivial([trivial.substitute({Y: X})]) == []
    assert make_non_trivial([eq.substitute({Y: X})]) == []
