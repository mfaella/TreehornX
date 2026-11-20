import io
from collections.abc import Iterator

import pytest

from treehornx.analysis.chc.system import CHCSystem
from treehornx.smt import sexpr as sx
from treehornx.smt import TRUE, Constant, Operator, OpExpr, Type, Var
from reset_env import reset_env, restore, snapshot


X = Var.make(name="x", type=Type.Int)
Y = Var.make(name="y", type=Type.Int)
B = Var.make(name="b", type=Type.Bool)
P = sx.Predicate.make(name="P", types=[Type.Int, Type.Bool])
Q = sx.Predicate.make(name="Q", types=[Type.Int])


def test_equal_nodes_are_the_same_object() -> None:
    assert sx.Application.make(predicate=P, args=(X, True)) is sx.Application.make(predicate=P, args=(X, TRUE))
    body = OpExpr.make(op=Operator.EQ, args=(Y, OpExpr.make(op=Operator.ADD, args=(X, 1))))
    assert sx.Clause.make(head=sx.Application.make(predicate=Q, args=(Y,)), body=(body,)) is sx.Clause.make(
        head=sx.Application.make(predicate=Q, args=(Y,)),
        body=(OpExpr.make(op=Operator.EQ, args=(Y, OpExpr.make(op=Operator.ADD, args=(X, 1)))),),
    )
    assert sx.Clause.make(head=sx.Application.make(predicate=Q, args=(Y,)), body=(body,)) is not sx.Clause.make(
        head=sx.Application.make(predicate=Q, args=(X,)), body=(body,)
    )
    assert sx.Predicate.make(name="P", types=(Type.Int, Type.Bool)) is P
    # the signature is part of the identity of a predicate
    assert sx.Predicate.make(name="P", types=[Type.Int]) is not P


@pytest.fixture
def private_cache() -> Iterator[None]:
    """Pools of this test only: they start empty (but TRUE and FALSE) and get their instances back at the end, so the
    module-level nodes of the other tests stay canonical."""
    saved = snapshot()
    reset_env()
    yield
    restore(saved)


@pytest.mark.usefixtures("private_cache")
def test_reset_env() -> None:
    """The CHC reset also empties the term caches."""
    var = Var.make(name="z", type=Type.Int)
    pred = sx.Predicate.make(name="Z", types=[Type.Int])
    app = sx.Application.make(predicate=pred, args=(var,))
    reset_env()
    assert Var.make(name="z", type=Type.Int) is not var
    assert sx.Predicate.make(name="Z", types=[Type.Int]) is not pred
    assert sx.Application.make(predicate=pred, args=(var,)) is not app
    assert Constant.make(value=True) is TRUE


def test_predicate_declaration() -> None:
    assert P.smt_declaration() == "(declare-fun P (Int Bool) Bool)"
    assert sx.Predicate.make(name="R", types=[]).smt_declaration() == "(declare-fun R () Bool)"


def test_application_arity_is_checked() -> None:
    with pytest.raises(AssertionError):
        sx.Application.make(predicate=Q, args=(X, Y))
    assert sx.Application.make(predicate=sx.Predicate.make(name="R", types=[]), args=()).to_smt() == "R"


def test_clause_closure() -> None:
    clause = sx.Clause.make(
        head=sx.Application.make(predicate=Q, args=(Y,)),
        body=(
            sx.Application.make(predicate=P, args=(X, B)),
            OpExpr.make(op=Operator.EQ, args=(Y, OpExpr.make(op=Operator.ADD, args=(X, 1)))),
            B,
        ),
    )
    assert clause.to_smt() == ("(assert (forall ((b Bool) (x Int) (y Int)) (=> (and (P x b) (= y (+ x 1)) b) (Q y))))")
    assert list(clause.applications()) == [
        sx.Application.make(predicate=Q, args=(Y,)),
        sx.Application.make(predicate=P, args=(X, B)),
    ]


def test_fact_and_query() -> None:
    assert sx.Clause.make(head=sx.Application.make(predicate=Q, args=(0,)), body=()).to_smt() == "(assert (Q 0))"
    assert (
        sx.Clause.make(
            head=sx.Application.make(predicate=Q, args=(X,)), body=(OpExpr.make(op=Operator.GT, args=(X, 0)),)
        ).to_smt()
        == "(assert (forall ((x Int)) (=> (> x 0) (Q x))))"
    )
    assert (
        sx.Clause.make(head=False, body=(sx.Application.make(predicate=Q, args=(X,)),)).to_smt()
        == "(assert (forall ((x Int)) (=> (Q x) false)))"
    )


def test_query_needs_an_application() -> None:
    with pytest.raises(AssertionError):
        sx.Clause.make(head=False, body=(OpExpr.make(op=Operator.GT, args=(X, 0)),))


def test_system_declares_used_predicates() -> None:
    unused = sx.Predicate.make(name="Unused", types=[Type.Int])
    system = CHCSystem(
        [Q, unused],
        [
            sx.Clause.make(
                head=sx.Application.make(predicate=Q, args=(X,)), body=(OpExpr.make(op=Operator.EQ, args=(X, 0)),)
            ),
            sx.Clause.make(head=False, body=(sx.Application.make(predicate=Q, args=(X,)),)),
        ],
    )
    expected = (
        "(set-logic HORN)\n"
        "(declare-fun Q (Int) Bool)\n"
        "\n"
        "(assert (forall ((x Int)) (=> (= x 0) (Q x))))\n"
        "(assert (forall ((x Int)) (=> (Q x) false)))\n"
        "(check-sat)\n"
    )
    assert system.to_smt() == expected
    out = io.StringIO()
    system.write(out)
    assert out.getvalue() == expected


R = sx.Predicate.make(name="R", types=[Type.Int])
EQ0 = OpExpr.make(op=Operator.EQ, args=(X, 0))
P_FACT = sx.Clause.make(head=sx.Application.make(predicate=P, args=(X, B)), body=(EQ0,))
P_STEP = sx.Clause.make(
    head=sx.Application.make(predicate=P, args=(OpExpr.make(op=Operator.ADD, args=(X, 1)), B)),
    body=(sx.Application.make(predicate=P, args=(X, B)),),
)
Q_FROM_P = sx.Clause.make(
    head=sx.Application.make(predicate=Q, args=(X,)), body=(sx.Application.make(predicate=P, args=(X, B)),)
)
R_FACT = sx.Clause.make(head=sx.Application.make(predicate=R, args=(X,)), body=(EQ0,))
Q_QUERY = sx.Clause.make(head=False, body=(sx.Application.make(predicate=Q, args=(X,)),))
R_QUERY = sx.Clause.make(head=False, body=(sx.Application.make(predicate=R, args=(X,)),))


def queries_system() -> CHCSystem:
    return CHCSystem([P, Q, R], [P_FACT, R_FACT, P_STEP, Q_QUERY, Q_FROM_P, R_QUERY])


def test_queries() -> None:
    assert queries_system().queries() == [Q_QUERY, R_QUERY]
