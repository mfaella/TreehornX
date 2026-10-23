import io

from treehornx.chc.clean import UnionFind, clean_clause
from treehornx.chc.Lab.system import to_system, write_smt2
from treehornx.chc.smt import sexpr as sx
from treehornx.chc.smt.preprocess import conjuncts


def ints(*names: str) -> list[sx.Var]:
    return [sx.Var(name, sx.Type.Int) for name in names]


def pred(arity: int, name: str = "P") -> sx.Predicate:
    return sx.Predicate(name, [sx.Type.Int] * arity)


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
    body = [sx.Application(p, x, w), sx.OpExpr(sx.Operator.EQ, x, y), sx.OpExpr(sx.Operator.EQ, y, z)]
    clause = clean_clause(sx.Clause(sx.Application(q, x, y, z), *body))
    assert clause is not None and isinstance(clause.head, sx.Application)
    # the head keeps its arity, with the same fresh variable three times
    assert len(set(clause.head.args)) == 1
    fresh = clause.head.args[0]
    assert fresh not in {x, y, z}
    assert clause.body == (sx.Application(p, fresh, w),)


def test_iff_between_booleans() -> None:
    a, b = sx.Var("a", sx.Type.Bool), sx.Var("b", sx.Type.Bool)
    p = sx.Predicate("B", [sx.Type.Bool, sx.Type.Bool])
    clause = clean_clause(
        sx.Clause(sx.Application(p, a, b), sx.OpExpr(sx.Operator.EQ, a, b), sx.OpExpr(sx.Operator.NOT, a))
    )
    assert clause is not None and isinstance(clause.head, sx.Application)
    assert clause.head.args[0] == clause.head.args[1]
    assert clause.body == (sx.OpExpr(sx.Operator.NOT, clause.head.args[0]),)


def test_equalities_below_the_top_level_are_not_merged() -> None:
    x, y, z = ints("x", "y", "z")
    p = pred(3)
    body = [
        sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, x, y)),
        sx.OpExpr(sx.Operator.OR, sx.OpExpr(sx.Operator.EQ, y, z), sx.OpExpr(sx.Operator.EQ, x, z)),
    ]
    clause = clean_clause(sx.Clause(sx.Application(p, x, y, z), *body))
    assert clause is not None
    assert clause.head == sx.Application(p, x, y, z)


def test_equality_with_a_term_or_a_constant_is_kept() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    body = [sx.OpExpr(sx.Operator.EQ, x, sx.OpExpr(sx.Operator.ADD, y, 1)), sx.OpExpr(sx.Operator.EQ, y, 0)]
    clause = clean_clause(sx.Clause(sx.Application(p, x, y), *body))
    assert clause is not None
    assert clause.head == sx.Application(p, x, y)
    assert set(clause.body) == set(body)


def test_nested_conjunctions_are_flattened() -> None:
    x, y, z = ints("x", "y", "z")
    p = pred(3)
    clause = clean_clause(
        sx.Clause(
            sx.Application(p, x, y, z),
            sx.OpExpr(sx.Operator.AND, sx.OpExpr(sx.Operator.EQ, x, y), sx.OpExpr(sx.Operator.GT, z, 0)),
        )
    )
    assert clause is not None and isinstance(clause.head, sx.Application)
    fresh = clause.head.args[0]
    assert clause.head.args == (fresh, fresh, z)
    assert list(clause.body) == list(conjuncts(sx.OpExpr(sx.Operator.GT, z, 0)))


def test_trivial_equalities_are_simplified_away() -> None:
    x, y = ints("x", "y")
    p = pred(1)
    clause = clean_clause(
        sx.Clause(
            sx.Application(p, x),
            sx.OpExpr(sx.Operator.EQ, x, y),
            sx.OpExpr(sx.Operator.EQ, y, x),
            sx.OpExpr(sx.Operator.EQ, x, x),
        )
    )
    # the body is only made of equalities between merged variables: a fact remains
    assert clause is not None and clause.body == ()
    assert isinstance(clause.head, sx.Application)


def test_query_stays_an_implication_to_false() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    clause = clean_clause(sx.Clause(False, sx.Application(p, x, y), sx.OpExpr(sx.Operator.EQ, x, y)))
    assert clause is not None and clause.head is False
    assert len(clause.body) == 1 and isinstance(clause.body[0], sx.Application)


def test_unsatisfiable_body_gives_no_clause() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    assert (
        clean_clause(
            sx.Clause(
                sx.Application(p, x, y),
                sx.OpExpr(sx.Operator.EQ, x, y),
                sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, x, y)),
            )
        )
        is None
    )


def test_empty_body_returns_the_head() -> None:
    x, y = ints("x", "y")
    head = sx.Application(pred(2), x, y)
    assert clean_clause(sx.Clause(head)) == sx.Clause(head)


def test_system_is_cleaned_when_printed() -> None:
    x, y = ints("x", "y")
    p = pred(2)
    fact = sx.Clause(sx.Application(p, x, y), sx.OpExpr(sx.Operator.EQ, x, y))
    valid = sx.Clause(
        sx.Application(p, x, y),
        sx.OpExpr(sx.Operator.EQ, x, y),
        sx.OpExpr(sx.Operator.NOT, sx.OpExpr(sx.Operator.EQ, x, y)),
    )
    query = sx.Clause(False, sx.Application(p, x, y), sx.OpExpr(sx.Operator.LT, x, y))
    raw = to_system([p], [fact, valid, query], clean=False)
    cleaned = to_system([p], [fact, valid, query], clean=True)
    assert raw.clauses == cleaned.clauses == [fact, valid, query]
    assert list(raw.printed_clauses()) == [fact, valid, query]
    printed = list(cleaned.printed_clauses())
    # the clause with an unsatisfiable body is dropped
    assert [c.head.predicate if c.head else c.head for c in printed] == [p, False]
    assert isinstance(printed[0].head, sx.Application) and printed[0].body == ()
    assert printed[0].head.args[0] == printed[0].head.args[1]
    out = io.StringIO()
    write_smt2([fact, valid, query], out, clean=True)
    assert out.getvalue().count("(assert") == len(printed)
