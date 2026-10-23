"""Compares z3, eldarica and the portfolio on the Lab and precondition test cases.

The CHC system of every case of `test_lab_chc.py` and `test_pre_chc.py` is built once and solved by every
solver (`z3` and `golem` in scripts/solvers, `eld` in tests/integration/solvers, PATH otherwise). For every case it
records the build time, the number of predicates and clauses, and the time and status of each solver; a solver
that crashes is reported as ERROR(...). For the portfolio it also records the racer deciding (`golem-<engine>` for
golem) and the command it ran.

Usage: uv run python scripts/benchmarks_solvers.py [--out FILE.json]
"""

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from integration import test_lab_chc, test_pre_chc  # noqa: E402
from integration.config import TestConfig, make_system  # noqa: E402
from treehornx.chc.solvers import (  # noqa: E402
    CHCSolver,
    EldaricaSolver,
    GolemSolver,
    PortfolioSolver,
    SolverError,
    Z3Solver,
)


SHIPPED = ROOT / "scripts" / "solvers" / "linux" / "x86-64"
TEST_SOLVERS = ROOT / "tests" / "integration" / "solvers"
SOLVERS: dict[str, CHCSolver] = {
    "z3": Z3Solver(SHIPPED),
    "eldarica": EldaricaSolver(TEST_SOLVERS),
    "portfolio": PortfolioSolver(
        solvers=[
            GolemSolver(SHIPPED, engine="spacer"),
            GolemSolver(SHIPPED, engine="pa"),
            Z3Solver(SHIPPED),
            EldaricaSolver(TEST_SOLVERS),
        ]
    ),
}


def jobs():
    """(suite, config) of every integration test case, the solver of the config is ignored."""
    suites = (
        ("lab", test_lab_chc.CASES),
        ("pre", test_pre_chc.CASES),
        ("lab(no pre)", test_pre_chc.WITHOUT_PRECONDITION),
    )
    for suite, cases in suites:
        for case in cases:
            config = case.values[0]
            assert isinstance(config, TestConfig)
            yield suite if config.pre is None else f"{suite}:{config.pre}", config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None, help="output JSON file")
    args = parser.parse_args()
    out: Path = args.out or Path(f"benchmarks_solvers_{time.strftime('%Y-%m-%d_%H-%M-%S')}.json")

    rows = []
    for suite, config in jobs():
        start = time.perf_counter()
        system = make_system(config)
        row = {
            "suite": suite,
            "program": config.program,
            "m": config.m,
            "expected": config.expected.name,
            "build_s": time.perf_counter() - start,
            "predicates": len(system.predicates),
            "clauses": len(system.clauses),
        }
        for name, solver in SOLVERS.items():
            start = time.perf_counter()
            try:
                if isinstance(solver, PortfolioSolver):
                    outcome = solver.race(system, config.timeout)
                    status = outcome.status.name
                    row[f"{name}_winner"] = None if outcome.solver is None else outcome.solver.label
                    row[f"{name}_command"] = None if outcome.command is None else list(outcome.command)
                else:
                    status = solver.solve(system, config.timeout).name
            except SolverError as e:
                status = f"ERROR({e})"
            row[f"{name}_s"] = time.perf_counter() - start
            row[f"{name}_status"] = status
        rows.append(row)
        print(json.dumps(row), flush=True)

    out.write_text(json.dumps(rows, indent=1))
    print(f"results written to {out}")


if __name__ == "__main__":
    main()
