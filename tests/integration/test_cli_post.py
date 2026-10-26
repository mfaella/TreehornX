"""The verify command checks the postcondition given by --post, under the precondition given by --pre."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from treehornx.chc.solvers import Z3Solver
from treehornx.feature_flags import FeatureFlags
from treehornx.main import POST, POST_CHECK, PRE, TREE_SHAPE, app, verify
from treehornx.parser import parse_file

from .config import C_FILES, solver_available, solver_dir


pytestmark = pytest.mark.skipif(not solver_available("z3"), reason="z3 not found")

PROGRAM = C_FILES / "sll_safe_shape_increment.c"


@pytest.mark.parametrize(("pre", "expected"), [(None, "unsat"), ("sll_sorted", "sat")])
def test_verify_reports_post(pre: str | None, expected: str) -> None:
    solver = Z3Solver(solver_dir("z3"))
    ctx = PRE[pre]() if pre else None
    stats = verify(
        parse_file(str(PROGRAM)), 128, 0, ctx, False, False, solver, 120, FeatureFlags(), post_ctx=POST["sll_sorted"]()
    )
    assert stats.outcome[POST_CHECK] == expected
    # the taints are enumerated for the postcondition alone
    assert TREE_SHAPE not in stats.outcome
    assert stats.tainted_labels_count > 0


def test_cli_dumps_the_post_system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["verify", str(PROGRAM), "--post", "sll_sorted", "--smt2"])
    assert result.exit_code == 0, result.output
    text = (tmp_path / f"{PROGRAM.stem}_{POST_CHECK}.smt2").read_text()
    assert "(declare-fun Post" in text
    # the states of the negated automaton: the node state and the trail states
    assert "p_post_n_error" in text and "_post_t" in text
