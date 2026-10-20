import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
import pytest
from pychc.environment import reset_env

from treehornx.chc.clean import UnionFind, clean_clause, conjuncts


@pytest.fixture(autouse=True)
def fresh_smt_environment() -> None:
    reset_env()


@pytest.fixture(autouse=True)
def enable_clean_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("treehornx.chc.clean.ENABLE_CLEAN_CLAUSE", True)


def ints(*names: str) -> list:
    return [smt.Symbol(name, smtty.INT) for name in names]


def pred(arity: int, name: str = "P"):
    return chc.Predicate(name, [smtty.INT] * arity)


def test_union_find_groups_in_insertion_order() -> None:
    uf = UnionFind[str]()
    uf.union("a", "b")
    uf.union("c", "d")
    uf.union("b", "d")
    uf.add("e")
    assert uf.groups() == [["a", "b", "c", "d"], ["e"]]


def test_transitive_class_becomes_one_fresh_variable() -> None:
    x, y, z, w = ints("x", "y", "z", "w")
    p, q = pred(2, "P"), pred(3, "Q")
    clause = clean_clause([chc.Apply(p, [x, w]), smt.Equals(x, y), smt.Equals(y, z)], chc.Apply(q, [x, y, z]))
    assert clause is not None and clause.is_implies()
    body, head = clause.arg(0), clause.arg(1)
    # the head keeps its arity, with the same fresh variable three times
    assert len(set(head.args())) == 1
    fresh = head.arg(0)
    assert fresh not in {x, y, z}
    assert body == chc.Apply(p, [fresh, w])


def test_iff_between_booleans() -> None:
    a, b = smt.Symbol("a"), smt.Symbol("b")
    p = chc.Predicate("B", [smtty.BOOL, smtty.BOOL])
    clause = clean_clause([smt.Iff(a, b), smt.Not(a)], chc.Apply(p, [a, b]))
    assert clause is not None
    body, head = clause.arg(0), clause.arg(1)
    assert head.arg(0) == head.arg(1)
    assert body == smt.Not(head.arg(0))


def test_equalities_below_the_top_level_are_not_merged() -> None:
    x, y, z = ints("x", "y", "z")
    p = pred(3)
    body = [smt.Not(smt.Equals(x, y)), smt.Or(smt.Equals(y, z), smt.Equals(x, z))]
    clause = clean_clause(body, chc.Apply(p, [x, y, z]))
    assert clause is not None
    assert clause.arg(1) == chc.Apply(p, [x, y, z])


def test_equality_with_a_term_or_a_constant_is_kept() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    body = [smt.Equals(x, smt.Plus(y, smt.Int(1))), smt.Equals(y, smt.Int(0))]
    clause = clean_clause(body, chc.Apply(p, [x, y]))
    assert clause is not None
    assert clause.arg(1) == chc.Apply(p, [x, y])
    assert set(conjuncts(clause.arg(0))) == set(body)


def test_trivial_equalities_are_simplified_away() -> None:
    x, y = ints("x", "y")
    p = pred(1)
    clause = clean_clause([smt.Equals(x, y), smt.Equals(y, x), smt.Equals(x, x)], chc.Apply(p, [x]))
    # the body is only made of equalities between merged variables: a fact remains
    assert clause is not None and not clause.is_implies()
    assert clause.is_function_application()


def test_query_stays_an_implication_to_false() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    clause = clean_clause([chc.Apply(p, [x, y]), smt.Equals(x, y)], smt.FALSE())
    assert clause is not None and clause.is_implies()
    assert clause.arg(1).is_false()


def test_unsatisfiable_body_gives_no_clause() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    assert clean_clause([smt.Equals(x, y), smt.Not(smt.Equals(x, y))], chc.Apply(p, [x, y])) is None


def test_empty_body_returns_the_head() -> None:
    x, y = ints("x", "y")
    head = chc.Apply(pred(2), [x, y])
    assert clean_clause([], head) == head
