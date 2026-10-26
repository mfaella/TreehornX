"""The states of the negated postcondition are arguments of the predicate of the tainted labels."""

from pathlib import Path

import pytest

from treehornx.chc.Post import PostRunner
from treehornx.chc.sdta.SDTAContext import not_sll_sorted_ctx, true_ctx
from treehornx.chc.TreeShape import TreeShapeCHC, build_tree_shape
from treehornx.enum_models.Taint import TaintedLabel
from treehornx.parser import parse_file


C_FILES = Path(__file__).parents[2] / "integration" / "c_files"
N = 24


@pytest.fixture(scope="module")
def runner() -> PostRunner:
    function = parse_file(str(C_FILES / "sll_safe_shape_increment.c"))
    k = function.node.k
    shape: TreeShapeCHC = build_tree_shape(function, k, 0, N)
    return PostRunner(
        function,
        shape.pairs,
        true_ctx(),
        k,
        0,
        sym=shape.lab.sym,
        n=N,
        engine=shape.engine,
        post=not_sll_sorted_ctx(),
    )


def _labels(runner: PostRunner) -> list[TaintedLabel]:
    return sorted(runner.labels, key=lambda label: runner.predicate(label).name)


def test_arity_counts_the_post_states(runner: PostRunner) -> None:
    states = len(runner.post.states)
    for label in _labels(runner):
        lab_arity = len(runner.sym.label_symbols(label.lab))
        post = runner.post_sym
        count = int(post.has_node_state(label)) + len(post.slots(label)) + len(label.taint_ptr)
        assert len(runner.node_data_types(label)) == lab_arity + count * states
        assert len(runner.node_data_symbols(label, "p_")) == len(runner.node_data_types(label))


def test_untainted_labels_have_no_node_state(runner: PostRunner) -> None:
    for label in _labels(runner):
        names = {var.name for var in runner.node_data_symbols(label, "p_")}
        has_node = any(name.startswith("p_post_n_") for name in names)
        assert has_node == (bool(label.taint_node) and label.lab.frame.active)


def test_output_nodes_apply_psi(runner: PostRunner) -> None:
    """Every output node has a state, so ψ of A¬post constrains it; some node is the output root."""
    output = [label for label in _labels(runner) if runner.post_sym.has_node_state(label)]
    assert output
    assert any(runner.is_output_root(label) for label in output)
    for label in output:
        local = runner.node_local_constraints(label, "p_")
        assert "p_post_n_error" in " ".join(map(str, local))
