"""Tainting: the extended Booleans, the pointer-taint vectors and the engine on a sorted-list insertion."""

from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Iterable

import pytest
from typing_extensions import override

from treehornx.chc.Lab import enumerate_labels
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Taint import BoolPlus, TaintedLabel, TaintingEngine, TaintPtr
from treehornx.parser import parse_file
from treehornx.symbolic import Edge, Pair, SymbolicEngine


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24

Bottom, Top, TopPlus = BoolPlus.Bottom, BoolPlus.Top, BoolPlus.TopPlus


def test_bool_plus_truthiness() -> None:
    assert not Bottom
    assert Top
    assert TopPlus


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (Bottom, Bottom, Bottom),
        (Bottom, Top, Top),
        (Top, Bottom, Top),
        (Top, TopPlus, TopPlus),
        (TopPlus, Top, TopPlus),
        (TopPlus, Bottom, TopPlus),
    ],
)
def test_bool_plus_join(a: BoolPlus, b: BoolPlus, expected: BoolPlus) -> None:
    assert a.join(b) is expected


def test_taint_ptr_defaults_to_bottom() -> None:
    assert TaintPtr()[(0, 2)] is Bottom
    assert len(TaintPtr()) == 0


def test_taint_ptr_stores_only_non_bottom_keys() -> None:
    taints = TaintPtr({(0, 2): Bottom, (1, 3): Top})
    assert list(taints) == [(1, 3)]
    assert TaintPtr({(0, 2): Bottom}) == TaintPtr()
    assert hash(TaintPtr({(0, 2): Bottom})) == hash(TaintPtr())


def test_taint_ptr_assigning_bottom_removes_the_key() -> None:
    taints = TaintPtr().set((0, 2), Top)
    assert taints[(0, 2)] is Top
    cleared = taints.set((0, 2), Bottom)
    assert (0, 2) not in cleared
    assert cleared == TaintPtr()


def test_taint_ptr_join_never_downgrades() -> None:
    taints = TaintPtr().join((0, 2), TopPlus).join((0, 2), Top)
    assert taints[(0, 2)] is TopPlus


@pytest.fixture(scope="module")
def engine() -> TaintingEngine:
    function = parse_file(str(C_FILES / "sll_safe_insert_sorted.c"))
    engine = TaintingEngine(enumerate_labels(function, function.node.k, 1, N))
    engine.fix()
    return engine


def test_root_is_tainted_plus(engine: TaintingEngine) -> None:
    assert any(state.taint_node is TopPlus for state in engine.states)


def test_inserted_node_is_tainted(engine: TaintingEngine) -> None:
    def inserted(state: TaintedLabel) -> bool:
        return not state.lab[1].active and state.lab.frame.active

    assert any(inserted(state) and state.taint_node for state in engine.states)


def test_input_successor_is_tainted_top(engine: TaintingEngine) -> None:
    """Rule 2: a structural child of a tainted node never overwritten is tainted ⊤."""
    assert any(state.lab[1].active and state.taint_node is Top for state in engine.states)


def test_only_tainted_ptr_keys_are_stored(engine: TaintingEngine) -> None:
    assert all(v for state in engine.states for _, v in state.taint_ptr.items())


def test_steppable(engine: TaintingEngine) -> None:
    """Some pairs take no step; some labels (the lifted initial labels, at least) take one."""
    assert any(pair not in engine.steppable for pair in engine.edges)
    assert any(state in engine.steppable for state in engine.states)
    assert engine.steppable <= engine.states | engine.edges


# ---------------------------------------------------------------------------
# finals
# ---------------------------------------------------------------------------


class ToyEngine(SymbolicEngine[str, int]):
    """An engine with no steps over a fixed graph: the roots are given, the leaves are the other states with no
    edges as parent."""

    def __init__(self, edges: set[Pair[str]], roots: set[str], arity: int):
        super().__init__(initial_edges=edges, start_states=set(), child_indexes=set(range(arity)))
        self.roots = roots

    @override
    def step_up(self, edge: Pair[str], /) -> Pair[str] | None:
        return None

    @override
    def step_down(self, edge: Pair[str], /) -> Pair[str] | None:
        return None

    @override
    def step_int(self, state: str, /) -> Iterable[str] | None:
        return None

    @override
    def is_leaf(self, s: str, /) -> bool:
        return s not in self.roots and not self.edge_parent_index.get(s)

    @override
    def is_root(self, s: str, /) -> bool:
        return s in self.roots


def run_finals(
    edges: list[tuple[str, str, int]],
    saturated: set[str],
    unsaturated_pairs: frozenset[Pair[str]] = frozenset(),
    arity: int | None = None,
    roots: frozenset[str] = frozenset({"R"}),
) -> tuple[set[str], set[Pair[str]]]:
    """`finals` on a toy graph rooted in `roots`: the states out of `saturated` and the pairs in
    `unsaturated_pairs` are steppable. The arity is one more than the largest child index of the edges by
    default."""
    pairs = {Edge(a, b, j) for a, b, j in edges}
    states = {s for pair in pairs for s in (pair.parent, pair.child)}
    if arity is None:
        arity = 1 + max(j for _, _, j in edges)
    engine = ToyEngine(pairs, set(roots), arity)
    engine.steppable |= (states - saturated) | set(unsaturated_pairs)
    finals = engine.finals()
    return set(finals.states), set(finals.edges)


def test_finals_cycle_falls_with_its_only_support() -> None:
    """B is supported only by A, which fails on another slot: both fall, whatever the visiting order."""
    states, pairs = run_finals([("R", "A", 0), ("A", "B", 0), ("A", "D", 1), ("B", "A", 0)], {"R", "A", "B"})
    assert states == set()
    assert pairs == set()


def test_finals_reject_an_infinite_tail() -> None:
    """T is supported only by itself: no finite tree, so T and R fall."""
    states, pairs = run_finals([("R", "T", 0), ("T", "T", 0)], {"R", "T"})
    assert states == set()
    assert pairs == set()


def test_finals_keep_a_cycle_with_a_base_case() -> None:
    """A is final through the leaf L; the self-loop of A is kept too."""
    states, pairs = run_finals([("R", "A", 0), ("A", "A", 0), ("A", "L", 0)], {"R", "A", "L"})
    assert states == {"R", "A", "L"}
    assert pairs == {Edge("R", "A", 0), Edge("A", "A", 0), Edge("A", "L", 0)}


def test_finals_do_not_depend_on_the_path() -> None:
    """B fails while A is on the path, but Z -> B -> A -> L is a finite tree: B is final from Z."""
    edges = [("R", "A", 0), ("Z", "B", 0), ("A", "B", 0), ("A", "L", 0), ("B", "A", 0)]
    states, _ = run_finals(edges, {"R", "Z", "A", "B", "L"}, roots=frozenset({"R", "Z"}))
    assert states == {"R", "Z", "A", "B", "L"}


def test_finals_leaves_and_unreachable_states() -> None:
    states, _ = run_finals([("R", "L", 0), ("U", "L", 0)], {"R", "L", "U"})
    assert states == {"R", "L"}


def test_finals_slot_with_only_unsaturated_pairs_removes_the_parent() -> None:
    states, _ = run_finals([("R", "A", 0), ("R", "B", 1)], {"R", "A", "B"}, frozenset({Edge("R", "B", 1)}))
    assert states == set()


def test_finals_parent_missing_a_child_index_falls_with_its_ancestors() -> None:
    """A has a pair for index 0 only: with arity 2 it has no clause, so A and the root R needing it fall."""
    states, pairs = run_finals([("R", "A", 0), ("R", "L", 1), ("A", "L", 0)], {"R", "A", "L"}, arity=2)
    assert states == set()
    assert pairs == set()


def test_finals_one_supported_alternative_is_enough() -> None:
    states, pairs = run_finals([("R", "A", 0), ("R", "D", 0)], {"R", "A"})
    assert states == {"R", "A"}
    assert pairs == {Edge("R", "A", 0)}


def test_engine_finals(engine: TaintingEngine) -> None:
    finals = engine.finals()
    states, pairs = finals.states, finals.edges
    assert any(state.taint_node is TopPlus for state in states)
    assert any(not state.lab[1].active and state.lab.frame.active and state.taint_node for state in states)
    for pair in pairs:
        assert pair not in engine.steppable
        assert pair.parent not in engine.steppable and pair.child not in engine.steppable
        assert pair.parent in states and pair.child in states


Tree = tuple[Lab, "list[Tree] | None"]


def concrete_trees(engine: TaintingEngine, depth: int) -> Iterable[Tree]:
    """The trees built from the final Lab pairs kept by the engine (no memory errors), up to depth; nodes with no
    pairs (never reached by the lace or allocated) are leaves."""
    labels, lab_pairs = engine.lab_finals()
    children: defaultdict[Lab, defaultdict[int, list[Lab]]] = defaultdict(lambda: defaultdict(list))
    for pair in lab_pairs:
        children[pair.parent][pair.j].append(pair.child)

    def trees(label: Lab, d: int) -> Iterable[Tree]:
        if len(label) == 1 or not children[label]:
            yield label, None
            return
        if d == 0:
            return
        options = [children[label][j] for j in range(engine.k + engine.m)]
        for combo in product(*options):
            for subtrees in product(*(list(trees(c, d - 1)) for c in combo)):
                yield label, list(subtrees)

    for root in labels:
        if is_initial(root):
            yield from trees(root, depth)


def saturate(engine: TaintingEngine, tree: Tree) -> tuple[list[TaintedLabel], list[tuple[int, int, int]]]:
    """The taints of a concrete tree, by a global fixpoint of the engine's steps."""
    nodes: list[TaintedLabel] = []
    edges: list[tuple[int, int, int]] = []

    def flatten(t: Tree) -> int:
        i = len(nodes)
        nodes.append(engine.initial(t[0]))
        for j, sub in enumerate(t[1] or []):
            edges.append((i, flatten(sub), j))
        return i

    flatten(tree)
    changed = True
    while changed:
        changed = False
        for i, state in enumerate(nodes):
            internal = engine.step_int(state)
            if internal is not None:
                nodes[i] = next(iter(internal))
                changed = True
        for a, b, j in edges:
            up = engine.step_up(Edge(nodes[a], nodes[b], j))
            if up is not None:
                nodes[a] = up.parent
                changed = True
            down = engine.step_down(Edge(nodes[a], nodes[b], j))
            if down is not None:
                nodes[b] = down.child
                changed = True
    return nodes, edges


def test_engine_finals_contain_every_saturated_tree(engine: TaintingEngine) -> None:
    finals = engine.finals()
    states, pairs = finals.states, finals.edges
    trees = list(concrete_trees(engine, depth=8))
    assert trees
    for tree in trees:
        nodes, edges = saturate(engine, tree)
        assert all(node in states for node in nodes)
        assert all(Edge(nodes[a], nodes[b], j) in pairs for a, b, j in edges)
