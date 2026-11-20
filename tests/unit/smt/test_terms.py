import gc
from collections.abc import Iterator

import pytest

from treehornx import smt as sx
from reset_env import reset_env, restore, snapshot


X = sx.Var.make(name="x", type=sx.Type.Int)
Y = sx.Var.make(name="y", type=sx.Type.Int)
B = sx.Var.make(name="b", type=sx.Type.Bool)


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        (sx.Constant.make(value=3), "3"),
        (sx.Constant.make(value=-3), "(- 3)"),
        (sx.TRUE, "true"),
        (sx.FALSE, "false"),
        (sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 1)), "(+ x 1)"),
        (sx.OpExpr.make(op=sx.Operator.DIV, args=(X, 2)), "(div x 2)"),
        (sx.OpExpr.make(op=sx.Operator.MOD, args=(X, 2)), "(mod x 2)"),
        (sx.OpExpr.make(op=sx.Operator.EQ, args=(B, True)), "(= b true)"),
        (sx.OpExpr.make(op=sx.Operator.NOT, args=(sx.OpExpr.make(op=sx.Operator.EQ, args=(X, Y)),)), "(not (= x y))"),
        (
            sx.OpExpr.make(op=sx.Operator.IMPLIES, args=(B, sx.OpExpr.make(op=sx.Operator.LT, args=(X, Y)))),
            "(=> b (< x y))",
        ),
        (sx.OpExpr.make(op=sx.Operator.ITE, args=(B, X, Y)), "(ite b x y)"),
        (sx.Max(X, Y), "(ite (>= x y) x y)"),
    ],
)
def test_printing(term: sx.SExpr, expected: str) -> None:
    assert term.to_smt() == expected


def test_types() -> None:
    assert sx.OpExpr.make(op=sx.Operator.ADD, args=(X, Y)).get_type() is sx.Type.Int
    assert sx.OpExpr.make(op=sx.Operator.ITE, args=(B, X, Y)).get_type() is sx.Type.Int
    assert sx.OpExpr.make(op=sx.Operator.ITE, args=(B, B, sx.FALSE)).get_type() is sx.Type.Bool
    assert sx.OpExpr.make(op=sx.Operator.EQ, args=(X, Y)).get_type() is sx.Type.Bool
    assert sx.TRUE.get_type() is sx.Type.Bool and sx.Constant.make(value=1).get_type() is sx.Type.Int


def test_bool_and_int_constants_differ() -> None:
    assert sx.Constant.make(value=True) is not sx.Constant.make(value=1)
    assert sx.Constant.make(value=1) not in {sx.Constant.make(value=True)}
    assert sx.Constant.make(value=1) is sx.Constant.make(value=1) and sx.Constant.make(value=1) != X
    assert sx.Constant.make(value=True) is sx.TRUE and sx.Constant.make(value=False) is sx.FALSE


def test_equal_terms_are_the_same_object() -> None:
    assert sx.Var.make(name="x", type=sx.Type.Int) is X
    assert sx.Var.make(name="x", type=sx.Type.Bool) is not X
    assert sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 1)) is sx.OpExpr.make(
        op=sx.Operator.ADD, args=(X, sx.Constant.make(value=1))
    )
    assert sx.OpExpr.make(op=sx.Operator.ADD, args=(X, 1)) is not sx.OpExpr.make(op=sx.Operator.ADD, args=(Y, 1))


@pytest.fixture
def private_cache() -> Iterator[None]:
    """Pools of this test only: they start empty (but TRUE and FALSE) and get their instances back at the end, so the
    module-level terms of the other tests stay canonical."""
    saved = snapshot()
    reset_env()
    yield
    restore(saved)


@pytest.mark.usefixtures("private_cache")
def test_reset_env() -> None:
    before = sx.Var.make(name="z", type=sx.Type.Int)
    assert sx.Var.make(name="z", type=sx.Type.Int) is before
    reset_env()
    after = sx.Var.make(name="z", type=sx.Type.Int)
    assert after is not before and after != before
    assert sx.Constant.make(value=True) is sx.TRUE and sx.Constant.make(value=False) is sx.FALSE


@pytest.mark.usefixtures("private_cache")
def test_unreferenced_terms_leave_the_cache() -> None:
    term = sx.OpExpr.make(op=sx.Operator.EQ, args=(sx.Var.make(name="z", type=sx.Type.Int), 0))
    assert len(pool_of(sx.OpExpr)) == 1 and len(pool_of(sx.Var)) == 1
    del term
    gc.collect()
    assert not pool_of(sx.OpExpr)
    gc.collect()  # z was still held by the term until the first collection
    assert not pool_of(sx.Var)


def test_max() -> None:
    assert sx.Max(X) is X
    assert sx.Max(3).to_smt() == "3"
    assert sx.Max(X, Y, 0).to_smt() == "(ite (>= (ite (>= x y) x y) 0) (ite (>= x y) x y) 0)"
