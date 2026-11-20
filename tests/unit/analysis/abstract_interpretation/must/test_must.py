"""The equality and constant must analyses on trees built by hand (`FakeLabel`, see `conftest.py`)."""

from __future__ import annotations

from must_helpers import FakeLabel, eq, sym

from treehornx import smt as sx
from treehornx.analysis.abstract_interpretation.ConstConstrTLab import ConstConstrTLab
from treehornx.analysis.abstract_interpretation.EqConstrTLab import EqConstrTLab
from treehornx.analysis.abstract_interpretation.MustConstantEngine import ConstFacts, MustConstantEngine
from treehornx.analysis.abstract_interpretation.MustEngine import BOTTOM, Bottom
from treehornx.analysis.abstract_interpretation.MustEqualityEngine import MustEqualityEngine
from treehornx.analysis.constraints.symbols import Parent, Slot, Symbol
from treehornx.analysis.engines.Edge import Edge
from treehornx.analysis.engines.SymbolicTree import SymbolicTree
from treehornx.utils import union_find as uf
from treehornx.utils.union_find import UnionFind


def tree(
    edges: list[tuple[FakeLabel, FakeLabel, int]], roots: list[FakeLabel], leaves: list[FakeLabel], arity: int = 1
):
    return SymbolicTree(frozenset(Edge(p, c, j) for p, c, j in edges), frozenset(roots), arity, frozenset(leaves))


def classes(f: UnionFind[sx.Var] | Bottom) -> set[frozenset[str]]:
    assert isinstance(f, UnionFind)
    return {frozenset(v.name for v in cls) for cls in uf.partition(f)}


def consts(f: ConstFacts | Bottom) -> dict[str, int | bool]:
    assert isinstance(f, ConstFacts)
    return {v.name: c.value for v, c in f.consts.items()}


def bool_sym(name: str) -> Symbol:
    return Symbol.make(base_name=name, type=sx.Type.Bool, role=None)


def S(*names: str) -> frozenset[str]:
    return frozenset(names)


# ============================================================================= UnionFind


class TestUnionFind:
    def test_of_and_partition(self) -> None:
        x, y, z, w = (sym(n) for n in "xyzw")
        u = uf.of([(x, y), (y, z)])
        assert classes(u) == {S("x", "y", "z")}
        assert uf.root(u, x) == uf.root(u, z) != uf.root(u, w)
        assert w not in u.parents  # root does not register w

    def test_join_is_the_union_of_the_classes(self) -> None:
        x, y, z = (sym(n) for n in "xyz")
        assert classes(uf.join(uf.of([(x, y)]), uf.of([(y, z)]))) == {S("x", "y", "z")}

    def test_meet_keeps_the_common_classes(self) -> None:
        x, y, z, w = (sym(n) for n in "xyzw")
        a = uf.of([(x, y), (y, z)])
        b = uf.of([(x, y), (z, w)])
        assert classes(uf.meet(a, b)) == {S("x", "y")}
        assert classes(uf.meet(a, UnionFind())) == set()

    def test_meet_does_not_modify_its_inputs(self) -> None:
        x, y, z = (sym(n) for n in "xyz")
        a, b = uf.of([(x, y)]), uf.of([(y, z)])
        _ = uf.meet(a, b)
        assert set(a.parents) == {x, y} and set(b.parents) == {y, z}

    def test_restrict_keeps_paths_through_dropped_variables(self) -> None:
        x, h, y = sym("x"), sym("h"), sym("y")
        assert classes(uf.restrict(uf.of([(x, h), (h, y)]), [x, y])) == {S("x", "y")}

    def test_transform_and_equal(self) -> None:
        x, y = sym("x"), sym("y")
        u = uf.of([(x, y)])
        assert classes(uf.transform(u, lambda v: v.with_role(Parent()))) == {S("p_x", "p_y")}
        assert uf.equal(u, uf.of([(y, x)]))
        assert not uf.equal(u, UnionFind())
        # singletons do not count
        single: UnionFind[sx.Var] = UnionFind()
        single[x]
        assert uf.equal(single, UnionFind())


# ============================================================================= equality engine


class TestEquality:
    def test_leaf_projects_through_quantified_symbols(self) -> None:
        leaf = FakeLabel("leaf", ["x", "y"], [eq(sym("x"), sym("h")), eq(sym("h"), sym("y"))])
        engine = MustEqualityEngine(tree([], [leaf], [leaf]))
        assert classes(engine.result(leaf)) == {S("x", "y")}

    def test_join_over_alternatives(self) -> None:
        # slot 0 of the root has two alternative children: x = y in both, y = z in one only
        c1 = FakeLabel("c1", ["a", "b", "c"], [eq(sym("a"), sym("b"))])
        c2 = FakeLabel("c2", ["a", "b", "c"], [eq(sym("a"), sym("b")), eq(sym("b"), sym("c"))])
        links = [("x", "a"), ("y", "b"), ("z", "c")]
        r = FakeLabel("r", ["x", "y", "z"], links={("c1", 0): links, ("c2", 0): links})
        engine = MustEqualityEngine(tree([(r, c1, 0), (r, c2, 0)], [r], [c1, c2]))
        assert classes(engine.result(r)) == {S("x", "y")}
        # top-down: each child keeps its own facts (the root adds nothing new)
        assert classes(engine.result(c2)) == {S("a", "b", "c")}

    def test_two_slots_compose(self) -> None:
        # slot 0 gives x = y, slot 1 gives y = z: the root has x = y = z
        c0 = FakeLabel("c0", ["a", "b"], [eq(sym("a"), sym("b"))])
        c1 = FakeLabel("c1", ["a", "b"], [eq(sym("a"), sym("b"))])
        r = FakeLabel(
            "r", ["x", "y", "z"], links={("c0", 0): [("x", "a"), ("y", "b")], ("c1", 1): [("y", "a"), ("z", "b")]}
        )
        engine = MustEqualityEngine(tree([(r, c0, 0), (r, c1, 1)], [r], [c0, c1], arity=2))
        assert classes(engine.result(r)) == {S("x", "y", "z")}

    def test_top_down_brings_the_facts_of_a_sibling(self) -> None:
        # c2 (slot 1) makes the root's a = b; the edge to c1 (slot 0) links u to a and v to b: c1 gets u = v
        c1 = FakeLabel("c1", ["u", "v"])
        c2 = FakeLabel("c2", ["s", "t"], [eq(sym("s"), sym("t"))])
        r = FakeLabel("r", ["a", "b"], links={("c1", 0): [("a", "u"), ("b", "v")], ("c2", 1): [("a", "s"), ("b", "t")]})
        t = tree([(r, c1, 0), (r, c2, 1)], [r], [c1, c2], arity=2)
        assert classes(MustEqualityEngine(t, top_down=False).result(c1)) == set()
        assert classes(MustEqualityEngine(t).result(c1)) == {S("u", "v")}

    def test_top_down_meets_before_the_join(self) -> None:
        # c has x = y; parent p1 adds y = z, parent p2 adds x = z: in both derivations x = y = z
        c = FakeLabel("c", ["x", "y", "z"], [eq(sym("x"), sym("y"))])
        w1 = FakeLabel("w1", ["s", "t"], [eq(sym("s"), sym("t"))])
        w2 = FakeLabel("w2", ["s", "t"], [eq(sym("s"), sym("t"))])
        p1 = FakeLabel(
            "p1",
            ["a", "b", "d"],
            links={("c", 0): [("a", "x"), ("b", "y"), ("d", "z")], ("w1", 1): [("b", "s"), ("d", "t")]},
        )
        p2 = FakeLabel(
            "p2",
            ["a", "b", "d"],
            links={("c", 0): [("a", "x"), ("b", "y"), ("d", "z")], ("w2", 1): [("a", "s"), ("d", "t")]},
        )
        t = tree([(p1, c, 0), (p1, w1, 1), (p2, c, 0), (p2, w2, 1)], [p1, p2], [c, w1, w2], arity=2)
        engine = MustEqualityEngine(t)
        assert classes(engine.result(c)) == {S("x", "y", "z")}
        # the join after the meet would give only x = y: the two contexts share nothing
        assert classes(engine.result(p1)) == {S("a", "b", "d")}
        assert classes(engine.result(p2)) == {S("a", "b", "d")}

    def test_list_cycle(self) -> None:
        # L -> L | E through slot 0, with x and y copied; E has x = y: every finite list ends in E, so L has x = y
        e = FakeLabel("E", ["x", "y"], [eq(sym("x"), sym("y"))])
        links = [("x", "x"), ("y", "y")]
        node = FakeLabel("L", ["x", "y"], links={("L", 0): links, ("E", 0): links})
        engine = MustEqualityEngine(tree([(node, node, 0), (node, e, 0)], [node], [e]))
        assert classes(engine.result(node)) == {S("x", "y")}

    def test_cycle_without_base_case_has_no_derivation(self) -> None:
        node = FakeLabel("L", ["x", "y"], [eq(sym("x"), sym("y"))], links={("L", 0): [("x", "x")]})
        engine = MustEqualityEngine(tree([(node, node, 0)], [node], []))
        engine.result(node)
        assert engine._bu_result[node] is BOTTOM  # pyright: ignore[reportPrivateUsage]
        # result() falls back to the label's own facts
        assert classes(engine.result(node)) == {S("x", "y")}

    def test_missing_slot_gives_bottom(self) -> None:
        c = FakeLabel("c", ["a"])
        r = FakeLabel("r", ["x"], links={("c", 0): [("x", "a")]})
        engine = MustEqualityEngine(tree([(r, c, 0)], [r], [c], arity=2))  # slot 1 has no child
        engine.result(r)
        assert engine._bu_result[r] is BOTTOM  # pyright: ignore[reportPrivateUsage]

    def test_root_that_is_also_a_child_keeps_its_bottom_up_result(self) -> None:
        e1 = FakeLabel("E1", ["x", "y"], [eq(sym("x"), sym("y"))])
        e2 = FakeLabel("E2", ["x", "y"])
        top = FakeLabel("T", ["x", "y"], links={("R", 0): [("x", "x"), ("y", "y")]}, cons=[eq(sym("x"), sym("y"))])
        r = FakeLabel("R", ["x", "y"], links={("E1", 0): [("x", "x"), ("y", "y")], ("E2", 0): [("x", "x")]})
        # R is a root and the child of T; as a root its derivations through E2 do not have x = y
        engine = MustEqualityEngine(tree([(top, r, 0), (r, e1, 0), (r, e2, 0)], [top, r], [e1, e2]))
        assert classes(engine.result(r)) == set()

    def test_apply(self) -> None:
        leaf = FakeLabel("leaf", ["x", "y", "z"], [eq(sym("y"), sym("z"))])
        out = MustEqualityEngine(tree([], [leaf], [leaf])).outputs()
        (new,) = out.labels
        assert isinstance(new, EqConstrTLab)
        # y and z leave the arguments; the new symbol I1 takes the place of y
        assert [s.name for s in new.args()] == ["x", "I1"]
        assert new.reps == {sym("y"): sym("I1"), sym("z"): sym("I1")}

    def test_eq_constr_tlab_from_classes(self) -> None:
        # a new symbol per class (I<k> for Int, B<k> for Bool) takes the place of the first argument of the class;
        # non-arguments are ignored; the order of the classes does not matter
        label = FakeLabel("l", ["a", "b1", "c", "d", "b2", "e"])
        classes = [{sym("e"), sym("c"), sym("h")}, {sym("d"), sym("a"), sym("zz")}, {sym("b2"), sym("b1")}]
        new = EqConstrTLab(label, classes)
        assert [s.name for s in new.args()] == ["I1", "B1", "I2"]
        assert new.reps == {
            sym("a"): sym("I1"),
            sym("d"): sym("I1"),
            sym("b1"): bool_sym("B1"),
            sym("b2"): bool_sym("B1"),
            sym("c"): sym("I2"),
            sym("e"): sym("I2"),
        }
        assert new == EqConstrTLab(label, list(reversed(classes)))
        assert [s.type for s in new.args()] == [sx.Type.Int, sx.Type.Bool, sx.Type.Int]

    def test_eq_constr_tlab_ignores_singleton_classes(self) -> None:
        label = FakeLabel("l", ["a", "b"])
        new = EqConstrTLab(label, [{sym("a")}, {sym("b"), sym("h")}])
        assert [s.name for s in new.args()] == ["a", "b"]
        assert not new.reps

    def test_eq_constr_tlab_twice_does_not_reuse_names(self) -> None:
        label = FakeLabel("l", ["a", "b", "c", "d"])
        first = EqConstrTLab(label, [{sym("a"), sym("b")}])
        assert [s.name for s in first.args()] == ["I1", "c", "d"]
        second = EqConstrTLab(first, [{sym("c"), sym("d")}])
        assert [s.name for s in second.args()] == ["I1", "I2"]

    def test_eq_constr_tlab_symbols_keep_the_quantified_ones(self) -> None:
        # h is quantified: it is a symbol of the label, not an argument; the new name skips it too
        label = FakeLabel("l", ["a", "b"], [eq(sym("a"), sym("h")), eq(sym("h"), sym("b"))])
        assert [s.name for s in label.symbols()] == ["a", "b", "h"]
        new = EqConstrTLab(label, [{sym("a"), sym("b")}])
        assert [s.name for s in new.args()] == ["I1"]
        assert [s.name for s in new.symbols()] == ["I1", "h"]
        assert [s.name for s in new.args(Parent())] == ["p_I1"]

    def test_eq_constr_tlab_constraints(self) -> None:
        label = FakeLabel(
            "l", ["a", "b", "c"], [eq(sym("a"), sym("b")), sx.OpExpr.make(op=sx.Operator.LT, args=(sym("b"), sym("c")))]
        )
        new = EqConstrTLab(label, [{sym("a"), sym("b")}])
        assert [c.to_smt() for c in new.constraints()] == ["(< I1 c)"]
        assert [c.to_smt() for c in new.constraints(Parent())] == ["(< p_I1 p_c)"]


# ============================================================================= constant engine


class TestConstant:
    def test_const_facts_make(self) -> None:
        x, y, z = sym("x"), sym("y"), sym("z")
        three, five = sx.Constant.make(value=3), sx.Constant.make(value=5)
        f = ConstFacts.make([(x, three), (z, five)], uf.of([(x, y)]))
        assert consts(f) == {"x": 3, "y": 3, "z": 5}
        assert ConstFacts.make([(x, three), (y, five)], uf.of([(x, y)])) is BOTTOM
        assert ConstFacts.make([(x, three), (x, five)], UnionFind()) is BOTTOM
        # value equality, though UnionFind has none
        assert f == ConstFacts.make([(y, three), (z, five)], uf.of([(y, x)]))
        assert f != ConstFacts.make([(x, three), (y, three), (z, five)], UnionFind())

    def test_leaf_constants_and_bools(self) -> None:
        leaf = FakeLabel(
            "leaf",
            ["x", "y", "b1", "b2"],
            [
                eq(sym("x"), 3),
                eq(sym("h"), sym("y")),
                eq(4, sym("h")),
                sym("b1"),
                sx.OpExpr.make(op=sx.Operator.NOT, args=(sym("b2"),)),
            ],
        )
        engine = MustConstantEngine(tree([], [leaf], [leaf]))
        assert consts(engine.result(leaf)) == {"x": 3, "y": 4, "b1": True, "b2": False}

    def test_constant_moves_up_an_edge(self) -> None:
        c = FakeLabel("c", ["a"], [eq(sym("a"), 7)])
        r = FakeLabel("r", ["x", "y"], [eq(sym("x"), sym("y"))], links={("c", 0): [("x", "a")]})
        engine = MustConstantEngine(tree([(r, c, 0)], [r], [c]))
        assert consts(engine.result(r)) == {"x": 7, "y": 7}

    def test_different_constants_in_alternatives_are_lost(self) -> None:
        c1 = FakeLabel("c1", ["a", "b"], [eq(sym("a"), 1), eq(sym("b"), 2)])
        c2 = FakeLabel("c2", ["a", "b"], [eq(sym("a"), 5), eq(sym("b"), 2)])
        links = [("x", "a"), ("y", "b")]
        r = FakeLabel("r", ["x", "y"], links={("c1", 0): links, ("c2", 0): links})
        engine = MustConstantEngine(tree([(r, c1, 0), (r, c2, 0)], [r], [c1, c2]))
        assert consts(engine.result(r)) == {"y": 2}

    def test_clash_drops_the_alternative(self) -> None:
        good = FakeLabel("good", ["a"], [eq(sym("a"), 3)])
        bad = FakeLabel("bad", ["a"], [eq(sym("a"), 5)])
        r = FakeLabel("r", ["x"], [eq(sym("x"), 3)], links={("good", 0): [("x", "a")], ("bad", 0): [("x", "a")]})
        engine = MustConstantEngine(tree([(r, good, 0), (r, bad, 0)], [r], [good, bad]))
        assert consts(engine.result(r)) == {"x": 3}
        # bad is a leaf with feasible facts, but no complete derivation goes through it
        assert engine._td_result[bad] is BOTTOM  # pyright: ignore[reportPrivateUsage]

    def test_all_alternatives_clash(self) -> None:
        bad = FakeLabel("bad", ["a"], [eq(sym("a"), 5)])
        r = FakeLabel("r", ["x"], [eq(sym("x"), 3)], links={("bad", 0): [("x", "a")]})
        engine = MustConstantEngine(tree([(r, bad, 0)], [r], [bad]))
        engine.result(r)
        assert engine._bu_result[r] is BOTTOM  # pyright: ignore[reportPrivateUsage]

    def test_label_that_clashes_by_itself(self) -> None:
        leaf = FakeLabel("leaf", ["x"], [eq(sym("x"), 1), eq(sym("x"), 2)])
        r = FakeLabel("r", ["y"], links={("leaf", 0): [("y", "x")]})
        engine = MustConstantEngine(tree([(r, leaf, 0)], [r], [leaf]))
        assert engine.result(leaf) is BOTTOM
        assert engine.result(r) == engine.label_facts(r)  # no derivation: the label's own facts
        out = engine.outputs()
        assert leaf in out.labels  # a state without derivation is kept unchanged

    def test_top_down_brings_a_constant_of_a_sibling(self) -> None:
        c1 = FakeLabel("c1", ["u"])
        c2 = FakeLabel("c2", ["s"], [eq(sym("s"), 9)])
        r = FakeLabel("r", ["a"], links={("c1", 0): [("a", "u")], ("c2", 1): [("a", "s")]})
        t = tree([(r, c1, 0), (r, c2, 1)], [r], [c1, c2], arity=2)
        assert consts(MustConstantEngine(t, top_down=False).result(c1)) == {}
        assert consts(MustConstantEngine(t).result(c1)) == {"u": 9}

    def test_list_cycle(self) -> None:
        # L -> L | E; E has x = 0; L copies x and sets y = 1: L has x = 0 and y = 1
        e = FakeLabel("E", ["x"], [eq(sym("x"), 0)])
        node = FakeLabel("L", ["x", "y"], [eq(sym("y"), 1)], links={("L", 0): [("x", "x")], ("E", 0): [("x", "x")]})
        engine = MustConstantEngine(tree([(node, node, 0), (node, e, 0)], [node], [e]))
        assert consts(engine.result(node)) == {"x": 0, "y": 1}

    def test_constant_on_an_edge(self) -> None:
        c = FakeLabel("c", ["a"])
        r = FakeLabel(
            "r", ["x"], extra={("c", 0): [eq(sym("x", Parent()), 4), eq(sym("a", Slot(0)), sym("x", Parent()))]}
        )
        engine = MustConstantEngine(tree([(r, c, 0)], [r], [c]))
        assert consts(engine.result(r)) == {"x": 4}
        assert consts(engine.result(c)) == {"a": 4}

    def test_apply(self) -> None:
        leaf = FakeLabel("leaf", ["x", "y"], [eq(sym("y"), 2)])
        (new,) = MustConstantEngine(tree([], [leaf], [leaf])).outputs().labels
        assert isinstance(new, ConstConstrTLab)
        assert [s.name for s in new.args()] == ["x"]
        assert new.consts == {sym("y"): sx.Constant.make(value=2)}
