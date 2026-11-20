"""SymbolicTree splits on a tree built by hand (string states).

    R1 ─┐
    R2 ─┴→ A → B ←─ R3        bodies: R1, R2: {A, B}   R3: {B}   R4: {}
    R6 → C → B, C → D                 R5: {E}        R6: {B, C, D}
    R5 → E          R4 (no children)

{B} is included in {A, B} and in {B, C, D} (both maximal): it goes into the smallest, {A, B}. The empty body of R4 is
included in every body: it goes into the smallest maximal one, {E}."""

import pytest

from treehornx.analysis.engines import Edge
from treehornx.analysis.engines.SymbolicTree import SymbolicTree, ordered


EDGES = [("R1", "A"), ("R2", "A"), ("A", "B"), ("R3", "B"), ("R6", "C"), ("C", "B"), ("C", "D"), ("R5", "E")]
PAIRS = frozenset(Edge(parent, child, 0) for parent, child in EDGES)
ROOTS = frozenset({"R1", "R2", "R3", "R4", "R5", "R6"})
TREE = SymbolicTree(PAIRS, ROOTS, 1, frozenset({"B", "D", "E"}))


def roots_of(trees: set[SymbolicTree[str]]) -> set[frozenset[str]]:
    return {tree.roots for tree in trees}


def test_body() -> None:
    assert TREE.body("R1") == {"A", "B"}
    assert TREE.body("R3") == {"B"}
    assert TREE.body("R4") == frozenset()
    assert TREE.body("R6") == {"B", "C", "D"}


def test_split_by_root() -> None:
    trees = TREE.split_by_root()
    assert roots_of(trees) == {frozenset({root}) for root in ROOTS}
    (r6,) = (tree for tree in trees if tree.roots == {"R6"})
    assert r6.labels == {"R6", "B", "C", "D"}
    assert r6.edges == {Edge("R6", "C", 0), Edge("C", "B", 0), Edge("C", "D", 0)}


def test_split_by_body() -> None:
    assert roots_of(TREE.split_by_body()) == {
        frozenset({"R1", "R2"}),
        frozenset({"R3"}),
        frozenset({"R4"}),
        frozenset({"R5"}),
        frozenset({"R6"}),
    }


def test_split_by_partial_body() -> None:
    trees = TREE.split_by_partial_body()
    assert roots_of(trees) == {frozenset({"R1", "R2", "R3"}), frozenset({"R4", "R5"}), frozenset({"R6"})}
    (abr,) = (tree for tree in trees if "R1" in tree.roots)
    assert abr.labels == {"R1", "R2", "R3", "A", "B"}
    assert abr.edges == {Edge("R1", "A", 0), Edge("R2", "A", 0), Edge("A", "B", 0), Edge("R3", "B", 0)}


@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_every_root_in_one_tree(level: int) -> None:
    roots = [root for tree in TREE.split(level) for root in tree.roots]
    assert sorted(roots) == sorted(ROOTS)


def test_split_levels() -> None:
    assert TREE.split(0) == {TREE}
    assert TREE.split(1) == TREE.split_by_partial_body()
    assert TREE.split(2) == TREE.split_by_body()
    assert TREE.split(3) == TREE.split_by_root()
    with pytest.raises(ValueError):
        TREE.split(4)


def test_ordered() -> None:
    index = {root: i for i, root in enumerate(TREE.roots)}
    trees = ordered(TREE.split_by_root(), TREE)
    assert [index[next(iter(tree.roots))] for tree in trees] == list(range(len(ROOTS)))
