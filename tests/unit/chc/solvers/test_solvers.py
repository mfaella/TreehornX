"""The solvers on tiny systems, piped on their standard input."""

import shutil
import stat
import time
from pathlib import Path

import pytest

from treehornx.chc.smt import sexpr as sx
from treehornx.chc.solvers import (
    CHCSolver,
    EldaricaSolver,
    GolemSolver,
    Outcome,
    PortfolioSolver,
    SolverError,
    Status,
    Z3Solver,
    base,
)


ROOT = Path(__file__).parents[4]
SOLVERS_DIRS = [ROOT / "scripts" / "solvers" / "linux" / "x86-64", ROOT / "tests" / "integration" / "solvers"]

X = sx.Var("x", sx.Type.Int)
P = sx.Predicate("P", [sx.Type.Int])


def system(bad: sx.SExpr) -> sx.CHCSystem:
    """P holds on 0, 1, 2, …: the query P(x) ∧ bad is reachable iff bad holds on some natural number."""
    return sx.CHCSystem(
        [P],
        [
            sx.Clause(sx.Application(P, X), sx.OpExpr(sx.Operator.EQ, X, 0)),
            sx.Clause(sx.Application(P, sx.OpExpr(sx.Operator.ADD, X, 1)), sx.Application(P, X)),
            sx.Clause(False, sx.Application(P, X), bad),
        ],
    )


def solver_dir(name: str) -> Path | None:
    return next((d for d in SOLVERS_DIRS if shutil.which(name, path=str(d))), None)


def available(cls: type[Z3Solver | EldaricaSolver | GolemSolver]) -> bool:
    return solver_dir(cls.NAME) is not None or shutil.which(cls.NAME) is not None


SOLVER_CLASSES = [
    pytest.param(cls, id=cls.NAME, marks=pytest.mark.skipif(not available(cls), reason=f"{cls.NAME} not found"))
    for cls in (Z3Solver, EldaricaSolver, GolemSolver)
]


@pytest.mark.parametrize("cls", SOLVER_CLASSES)
def test_sat_and_unsat(cls: type[Z3Solver | EldaricaSolver | GolemSolver]) -> None:
    solver: CHCSolver = cls(solver_dir(cls.NAME))
    assert solver.solve(system(sx.OpExpr(sx.Operator.LT, X, 0)), timeout=60) is Status.SAT
    assert solver.solve(system(sx.OpExpr(sx.Operator.EQ, X, 5))) is Status.UNSAT


def fake_solver(tmp_path: Path, name: str, script: str) -> Path:
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\ncat > /dev/null\n{script}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return tmp_path


def test_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SolverError, match="z3 not found"):
        Z3Solver(tmp_path)
    with pytest.raises(SolverError, match="on PATH"):
        EldaricaSolver()


def test_output_without_status(tmp_path: Path) -> None:
    solver = Z3Solver(fake_solver(tmp_path, "z3", "echo '(error \"line 1: bad input\")'"))
    with pytest.raises(SolverError, match="bad input"):
        solver.solve(system(sx.TRUE))


@pytest.mark.parametrize(("output", "status"), [("timeout", Status.UNKNOWN), ("unknown", Status.UNKNOWN)])
def test_gives_up(tmp_path: Path, output: str, status: Status) -> None:
    solver = EldaricaSolver(fake_solver(tmp_path, "eld", f"echo {output}"))
    assert solver.solve(system(sx.TRUE), timeout=10) is status


def test_killed_after_the_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "KILL_GRACE", 0)
    solver = Z3Solver(fake_solver(tmp_path, "z3", "sleep 30"))
    assert solver.solve(system(sx.TRUE), timeout=1) is Status.UNKNOWN


def test_solver_exiting_early(tmp_path: Path) -> None:
    """The solver does not read the system: writing it fails, the status printed is still read."""
    path = tmp_path / "z3"
    path.write_text("#!/bin/sh\necho sat\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    big = sx.CHCSystem([P], [sx.Clause(sx.Application(P, i)) for i in range(50_000)])
    assert Z3Solver(tmp_path).solve(big) is Status.SAT


PORTFOLIO = (GolemSolver, Z3Solver, EldaricaSolver)


def fake_portfolio(tmp_path: Path, scripts: dict[str, str]) -> PortfolioSolver:
    """Every solver of the portfolio replaced by a script, which must find the system in the file it is given."""
    for name, script in scripts.items():
        fake_solver(tmp_path, name, f'grep -q check-sat "$(eval echo \\${{$#}})" || exit 1\n{script}')
    return PortfolioSolver(tmp_path)


@pytest.mark.skipif(not all(available(cls) for cls in PORTFOLIO), reason="a solver of the portfolio is not found")
def test_portfolio_sat_and_unsat() -> None:
    solver = PortfolioSolver(solvers=[cls(solver_dir(cls.NAME)) for cls in PORTFOLIO])
    assert solver.solve(system(sx.OpExpr(sx.Operator.LT, X, 0)), timeout=60) is Status.SAT
    assert solver.solve(system(sx.OpExpr(sx.Operator.EQ, X, 5)), timeout=60) is Status.UNSAT


def test_portfolio_first_answer_wins(tmp_path: Path) -> None:
    solver = fake_portfolio(tmp_path, {"golem": "sleep 30", "z3": "echo unknown", "eld": "sleep 1; echo unsat"})
    start = time.perf_counter()
    outcome = solver.race(system(sx.TRUE))
    assert time.perf_counter() - start < 10, "the solvers still running are not killed"
    assert outcome.status is Status.UNSAT
    assert outcome.solver is not None and outcome.solver.label == "eld"
    assert outcome.command is not None and outcome.command[0] == str(tmp_path / "eld")


def test_portfolio_reports_the_golem_engine(tmp_path: Path) -> None:
    solver = fake_portfolio(
        tmp_path, {"golem": '[ "$2" = pa ] && echo sat || sleep 30', "z3": "sleep 30", "eld": "sleep 30"}
    )
    outcome = solver.race(system(sx.TRUE))
    assert outcome.status is Status.SAT
    assert outcome.solver is not None and outcome.solver.label == "golem-pa"
    assert outcome.command is not None and outcome.command[1:3] == ("-e", "pa")


def test_golem_engine(tmp_path: Path) -> None:
    path = tmp_path / "system.smt2"
    golem = GolemSolver(fake_solver(tmp_path, "golem", "echo sat"), engine="spacer")
    assert golem.file_command(path, None) == [str(tmp_path / "golem"), "-e", "spacer", str(path)]
    assert golem.label == "golem-spacer"
    assert GolemSolver(tmp_path).label == "golem"


def test_portfolio_unknown_when_none_decides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base, "KILL_GRACE", 0)
    solver = fake_portfolio(tmp_path, {"golem": "sleep 30", "z3": "echo unknown", "eld": "echo boom"})
    assert solver.race(system(sx.TRUE), timeout=1) == Outcome(Status.UNKNOWN)


def test_portfolio_every_solver_fails(tmp_path: Path) -> None:
    solver = fake_portfolio(tmp_path, {"golem": "echo golem failed", "z3": "echo z3 failed", "eld": "exit 3"})
    with pytest.raises(SolverError, match="golem failed"):
        solver.solve(system(sx.TRUE))


def test_golem_killed_at_the_timeout(tmp_path: Path) -> None:
    """Golem takes no timeout, it is killed when the timeout expires, without grace."""
    solver = GolemSolver(fake_solver(tmp_path, "golem", "sleep 30"))
    assert solver.kill_timeout(1) == 1
    assert solver.solve(system(sx.TRUE), timeout=1) is Status.UNKNOWN
