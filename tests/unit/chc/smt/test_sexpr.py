import gc
import io
from weakref import WeakValueDictionary

import pytest

from treehornx.chc.smt import sexpr as sx


X = sx.Var("x", sx.Type.Int)
Y = sx.Var("y", sx.Type.Int)
B = sx.Var("b", sx.Type.Bool)
P = sx.Predicate("P", [sx.Type.Int, sx.Type.Bool])
Q = sx.Predicate("Q", [sx.Type.Int])


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        (sx.Constant(3), "3"),
        (sx.Constant(-3), "(- 3)"),
        (sx.TRUE, "true"),
        (sx.FALSE, "false"),
        (sx.OpExpr(sx.Operator.ADD, X, 1), "(+ x 1)"),
        (sx.OpExpr(sx.Operator.DIV, X, 2), "(div x 2)"),
        (sx.OpExpr(sx.Operator.MOD, X, 2), "(mod x 2)"),
        (sx.OpExpr(sx.Operator.EQ, B, True), "(= b true)"),
        (sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, X, Y)), "(not (= x y))"),
        (sx.OpExpr(sx.Operator.IMPLIES, B, sx.OpExpr(sx.Operator.LT, X, Y)), "(=> b (< x y))"),
        (sx.OpExpr(sx.Operator.ITE, B, X, Y), "(ite b x y)"),
        (sx.Max(X, Y), "(ite (>= x y) x y)"),
    ],
)
def test_printing(term: sx.SExpr, expected: str) -> None:
    assert term.to_smt() == expected


def test_types() -> None:
    assert sx.OpExpr(sx.Operator.ADD, X, Y).get_type() is sx.Type.Int
    assert sx.OpExpr(sx.Operator.ITE, B, X, Y).get_type() is sx.Type.Int
    assert sx.OpExpr(sx.Operator.ITE, B, B, sx.FALSE).get_type() is sx.Type.Bool
    assert sx.OpExpr(sx.Operator.EQ, X, Y).get_type() is sx.Type.Bool
    assert sx.TRUE.get_type() is sx.Type.Bool and sx.Constant(1).get_type() is sx.Type.Int


def test_bool_and_int_constants_differ() -> None:
    assert sx.Constant(True) is not sx.Constant(1)
    assert sx.Constant(1) not in {sx.Constant(True)}
    assert sx.Constant(1) is sx.Constant(1) and sx.Constant(1) != X
    assert sx.Constant(True) is sx.TRUE and sx.Constant(False) is sx.FALSE


def test_equal_terms_are_the_same_object() -> None:
    assert sx.Var("x", sx.Type.Int) is X
    assert sx.Var("x", sx.Type.Bool) is not X
    assert sx.OpExpr(sx.Operator.ADD, X, 1) is sx.OpExpr(sx.Operator.ADD, X, sx.Constant(1))
    assert sx.Application(P, X, True) is sx.Application(P, X, sx.TRUE)
    body = sx.OpExpr(sx.Operator.EQ, Y, sx.OpExpr(sx.Operator.ADD, X, 1))
    assert sx.Clause(sx.Application(Q, Y), body) is sx.Clause(
        sx.Application(Q, Y), sx.OpExpr(sx.Operator.EQ, Y, sx.OpExpr(sx.Operator.ADD, X, 1))
    )
    assert sx.Clause(sx.Application(Q, Y), body) is not sx.Clause(sx.Application(Q, X), body)
    assert sx.Predicate("P", (sx.Type.Int, sx.Type.Bool)) is P
    # the signature is part of the identity of a predicate
    assert sx.Predicate("P", [sx.Type.Int]) is not P


@pytest.fixture
def private_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caches of this test only, so that resetting them leaves the module-level terms of the other tests canonical."""
    for name in ("_ints", "_bools", "_op_exprs", "_predicates", "_applications", "_clauses"):
        monkeypatch.setattr(sx, name, WeakValueDictionary[object, object]())
    monkeypatch.setattr(sx, "_vars", {t: WeakValueDictionary[str, sx.Var]() for t in sx.Type})


@pytest.mark.usefixtures("private_cache")
def test_reset_env() -> None:
    before = sx.Var("z", sx.Type.Int)
    assert sx.Var("z", sx.Type.Int) is before
    sx.reset_env()
    after = sx.Var("z", sx.Type.Int)
    assert after is not before and after != before
    assert sx.Constant(True) is sx.TRUE and sx.Constant(False) is sx.FALSE


@pytest.mark.usefixtures("private_cache")
def test_unreferenced_terms_leave_the_cache() -> None:
    term = sx.OpExpr(sx.Operator.EQ, sx.Var("z", sx.Type.Int), 0)
    assert len(sx._op_exprs) == 1 and len(sx._vars[sx.Type.Int]) == 1  # pyright: ignore[reportPrivateUsage]
    del term
    gc.collect()
    assert not sx._op_exprs  # pyright: ignore[reportPrivateUsage]
    gc.collect()  # z was still held by the term until the first collection
    assert not sx._vars[sx.Type.Int]  # pyright: ignore[reportPrivateUsage]


def test_max() -> None:
    assert sx.Max(X) is X
    assert sx.Max(3).to_smt() == "3"
    assert sx.Max(X, Y, 0).to_smt() == "(ite (>= (ite (>= x y) x y) 0) (ite (>= x y) x y) 0)"


def test_predicate_declaration() -> None:
    assert P.smt_declaration() == "(declare-fun P (Int Bool) Bool)"
    assert sx.Predicate("R", []).smt_declaration() == "(declare-fun R () Bool)"


def test_application_arity_is_checked() -> None:
    with pytest.raises(AssertionError):
        sx.Application(Q, X, Y)
    assert sx.Application(sx.Predicate("R", [])).to_smt() == "R"


def test_clause_closure() -> None:
    clause = sx.Clause(
        sx.Application(Q, Y), sx.Application(P, X, B), sx.OpExpr(sx.Operator.EQ, Y, sx.OpExpr(sx.Operator.ADD, X, 1)), B
    )
    assert clause.to_smt() == ("(assert (forall ((b Bool) (x Int) (y Int)) (=> (and (P x b) (= y (+ x 1)) b) (Q y))))")
    assert list(clause.applications()) == [sx.Application(Q, Y), sx.Application(P, X, B)]


def test_fact_and_query() -> None:
    assert sx.Clause(sx.Application(Q, 0)).to_smt() == "(assert (Q 0))"
    assert (
        sx.Clause(sx.Application(Q, X), sx.OpExpr(sx.Operator.GT, X, 0)).to_smt()
        == "(assert (forall ((x Int)) (=> (> x 0) (Q x))))"
    )
    assert sx.Clause(False, sx.Application(Q, X)).to_smt() == "(assert (forall ((x Int)) (=> (Q x) false)))"


def test_query_needs_an_application() -> None:
    with pytest.raises(AssertionError):
        sx.Clause(False, sx.OpExpr(sx.Operator.GT, X, 0))


def test_system_declares_used_predicates() -> None:
    unused = sx.Predicate("Unused", [sx.Type.Int])
    system = sx.CHCSystem(
        [Q, unused],
        [sx.Clause(sx.Application(Q, X), sx.OpExpr(sx.Operator.EQ, X, 0)), sx.Clause(False, sx.Application(Q, X))],
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


def test_transform_runs_when_printing() -> None:
    """The transform rewrites each clause as it is printed, the system keeps the clauses as built."""
    calls: list[sx.Clause] = []

    def drop_facts(clause: sx.Clause) -> sx.Clause | None:
        calls.append(clause)
        return None if clause.head == sx.Application(P, X, B) else clause

    fact = sx.Clause(sx.Application(P, X, B), sx.OpExpr(sx.Operator.EQ, X, 0))
    query = sx.Clause(False, sx.Application(Q, X))
    system = sx.CHCSystem([P, Q], [fact, query], drop_facts)
    assert not calls and system.clauses == [fact, query]
    printed = system.printed_clauses()
    assert not calls  # lazily, one clause at a time
    assert list(printed) == [query]
    out = io.StringIO()
    system.write(out)
    # P only occurs in the dropped clause: it is not declared
    assert out.getvalue() == system.to_smt()
    assert "declare-fun P" not in out.getvalue() and "(declare-fun Q (Int) Bool)" in out.getvalue()
    # printed_clauses, write, to_smt: every clause is rewritten at each printing
    assert calls == [fact, query] * 3
