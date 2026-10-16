"""Compares golem and eldarica on the Lab and precondition test cases.

The CHC system of every case of `test_lab_chc.py` and `test_pre_chc.py` is built once and solved by both
solvers (`golem` and `eld` in tests/integration/solvers). For every case it records the build time, the
number of predicates and clauses, and the time and status of each solver; a solver that crashes is reported
as ERROR(...).

Usage: uv run python scripts/benchmarks_solvers.py [--out FILE.json]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from pychc.environment import reset_env  # noqa: E402
from pychc.exceptions import PyCHCSolverException  # noqa: E402
from pychc.solvers.eldarica import EldaricaSolver  # noqa: E402
from pychc.solvers.golem import GolemSolver  # noqa: E402

import test_lab_chc as lab_tests  # noqa: E402
import test_pre_chc as pre_tests  # noqa: E402
from treehornx.chc import Lab, pre  # noqa: E402
from treehornx.parser import parse_file  # noqa: E402

SOLVERS = ROOT / "tests" / "integration" / "solvers"
C_FILES = ROOT / "tests" / "integration" / "c_files"
TIMEOUT = lab_tests.TIMEOUT
N = lab_tests.N


def values(case):
    """The arguments of a test case, also when it is wrapped in a pytest.param."""
    return tuple(case.values) if hasattr(case, "values") else case


def jobs():
    for program, m, expected in map(values, lab_tests.CASES):
        yield "lab", program, m, expected, lambda f, m=m: Lab.make_system(f, f.node.k, m, N, lab_tests.ends_with_error)
    for program, ctx, m, expected in map(values, pre_tests.CASES):
        yield f"pre:{ctx.__name__}", program, m, expected, lambda f, m=m, ctx=ctx: pre.make_system(f, f.node.k, m, N, ctx())
    for program in pre_tests.NEEDS_PRECONDITION:
        yield "lab(no pre)", program, 0, lab_tests.Status.UNSAT, lambda f: Lab.make_system(
            f, f.node.k, 0, N, pre_tests.ends_with_error
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None, help="output JSON file")
    args = parser.parse_args()
    out: Path = args.out or Path(f"benchmarks_solvers_{time.strftime('%Y-%m-%d_%H-%M-%S')}.json")

    rows = []
    for suite, program, m, expected, build in jobs():
        reset_env()
        function = parse_file(str(C_FILES / f"{program}.c"))
        start = time.perf_counter()
        system = build(function)
        row = {
            "suite": suite,
            "program": program,
            "m": m,
            "expected": expected.name,
            "build_s": time.perf_counter() - start,
            "predicates": len(list(system.get_predicates())),
            "clauses": len(list(system.get_clauses())),
        }
        for name, cls in (("golem", GolemSolver), ("eldarica", EldaricaSolver)):
            solver = cls(binary_path=SOLVERS)
            solver.load_system(system)
            start = time.perf_counter()
            try:
                status = solver.solve(timeout=TIMEOUT).name
            except PyCHCSolverException as e:
                status = f"ERROR({e})"
            row[f"{name}_s"] = time.perf_counter() - start
            row[f"{name}_status"] = status
        rows.append(row)
        print(json.dumps(row), flush=True)

    out.write_text(json.dumps(rows, indent=1))
    print(f"results written to {out}")


if __name__ == "__main__":
    main()
