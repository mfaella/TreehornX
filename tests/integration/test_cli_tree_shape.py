"""The verify command checks the tree shape with --tree-shape, under the precondition given by --pre."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from treehornx.chc.solvers import Z3Solver
from treehornx.feature_flags import FeatureFlags
from treehornx.main import PRE, TREE_SHAPE, app, verify
from treehornx.parser import parse_file

from .config import C_FILES, solver_available, solver_dir


pytestmark = pytest.mark.skipif(not solver_available("z3"), reason="z3 not found")

PROGRAM = C_FILES / "bst_pre_shape_left_greater.c"


@pytest.mark.parametrize(("pre", "expected"), [(None, "unsat"), ("bst", "sat")])
def test_verify_reports_tree_shape(pre: str | None, expected: str) -> None:
    solver = Z3Solver(solver_dir("z3"))
    ctx = PRE[pre]() if pre else None
    stats = verify(parse_file(str(PROGRAM)), 128, 0, ctx, False, False, solver, 120, FeatureFlags(), tree_shape=True)
    assert stats.outcome[TREE_SHAPE] == expected
    assert stats.tainted_labels_count > 0


def test_verify_without_tree_shape_skips_it() -> None:
    stats = verify(
        parse_file(str(PROGRAM)), 128, 0, None, False, False, Z3Solver(solver_dir("z3")), 120, FeatureFlags()
    )
    assert TREE_SHAPE not in stats.outcome


def test_cli_dumps_the_tree_shape_system(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["verify", str(PROGRAM), "--tree-shape", "--pre", "bst", "--smt2"])
    assert result.exit_code == 0, result.output
    dumped = tmp_path / f"{PROGRAM.stem}_{TREE_SHAPE}.smt2"
    text = dumped.read_text()
    assert "(set-logic HORN)" in text and "(check-sat)" in text
    assert "(declare-fun TreeShape" in text
    # the states of the bst automaton: the precondition is part of the system
    assert "pre_p_min" in text and "pre_p_max" in text


def test_cli_solves_the_tree_shape_system() -> None:
    solvers_dir = solver_dir("z3")
    args = ["verify", str(PROGRAM), "--tree-shape", "--pre", "bst", "--check-sat"]
    if solvers_dir is not None:
        args += ["--solvers-dir", str(solvers_dir)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert TREE_SHAPE in result.output
