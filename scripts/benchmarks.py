"""Runs every integration test case as a benchmark and dumps the measurements in a CSV file.

For every case it records:
- the time spent enumerating the labels, the time to build the CHCs on top of them and to serialize the system;
- the number of predicates (Lab, precondition) and of clauses;
- the number of queries by type;
- the precondition used;
- the solver time and status, compared with the status expected by the test.

Usage: uv run python scripts/benchmarks.py [--timeout SECONDS] [--only SUBSTRING] [--out FILE.csv]
"""

import argparse
import csv
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, TypeAlias

from treehornx import ir
from treehornx.chc import pre
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.sdta.SDTAContext import (
    SDTAContext,
    bst_strict_ctx,
    sll_sorted_ctx,
    sll_sorted_strict_ctx,
)
from treehornx.chc.smt.sexpr import Application, CHCSystem, Clause
from treehornx.chc.solvers import SolverError, Status, Z3Solver
from treehornx.enum_models.core.SymbolicEngine import SymbolicEngine
from treehornx.enum_models.Lab import LabEngine
from treehornx.feature_flags import FeatureFlags
from treehornx.parser import parse_file


ROOT = Path(__file__).parent.parent
C_FILES = ROOT / "tests" / "integration" / "c_files"
SOLVERS = ROOT / "scripts" / "solvers" / "linux" / "x86-64"
DEFAULT_TIMEOUT = 1800
N = 128

ERR_ONLY = frozenset({ExitCodeKind.ERR})

Ctx: TypeAlias = Callable[[], SDTAContext]


# ---------------------------------------------------------------------------
# cases: one per integration test
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    test: str
    """The integration test the case comes from."""
    program: str
    kind: str
    """`lab` (memory safety) or `pre` (memory safety under a precondition)."""
    m: int
    expected: Status
    n: int = N
    pre: Ctx | None = None
    exit_codes: frozenset[ExitCodeKind] = ERR_ONLY


def lab_cases() -> list[Case]:
    cases = [
        ("sll_safe_find", 0, Status.SAT),
        ("sll_unsafe_find", 0, Status.UNSAT),
        ("sll_safe_insert_sorted", 1, Status.SAT),
        ("sll_unsafe_insert", 1, Status.UNSAT),
        ("sll_safe_length", 0, Status.SAT),
        ("sll_unsafe_length", 0, Status.UNSAT),
        ("sll_safe_find_last", 0, Status.SAT),
        ("sll_unsafe_find_last", 0, Status.UNSAT),
        ("bst_safe_find", 0, Status.SAT),
        ("bst_unsafe_find", 0, Status.UNSAT),
        ("bst_safe_insert", 1, Status.SAT),
        ("bst_unsafe_insert", 1, Status.UNSAT),
    ]
    return [Case("test_lab_chc::test_memory_safety", p, "lab", m, e) for p, m, e in cases]


def pre_cases() -> list[Case]:
    test = "test_pre_chc::test_memory_safety_under_precondition"
    return [
        Case(test, "sll_sorted_safe_first_lt_last", "pre", 0, Status.SAT, pre=sll_sorted_strict_ctx),
        Case(test, "sll_sorted_unsafe_first_lt_last", "pre", 0, Status.UNSAT, pre=sll_sorted_strict_ctx),
        Case(test, "bst_safe_min_lt_max", "pre", 0, Status.SAT, pre=bst_strict_ctx),
        Case(test, "bst_unsafe_min_lt_max", "pre", 0, Status.UNSAT, pre=bst_strict_ctx),
        Case(test, "sll_safe_find", "pre", 0, Status.SAT, pre=sll_sorted_ctx),
        *(
            Case("test_pre_chc::test_unsafe_without_precondition", p, "lab", 0, Status.UNSAT)
            for p in ["sll_sorted_safe_first_lt_last", "bst_safe_min_lt_max"]
        ),
    ]


CASES = [*lab_cases(), *pre_cases()]


# ---------------------------------------------------------------------------
# measurements
# ---------------------------------------------------------------------------


@contextmanager
def enumeration_timer() -> Iterator[tuple[defaultdict[type, float], dict[int, Any]]]:
    """Times every `SymbolicEngine.fix` run in the block, by engine class, and collects the labels of those
    engines by id."""
    elapsed: defaultdict[type, float] = defaultdict(float)
    labels: dict[int, Any] = {}
    original = SymbolicEngine.fix

    def timed_fix(self: SymbolicEngine[Any]) -> Any:
        start = time.perf_counter()
        try:
            return original(self)
        finally:
            elapsed[type(self)] += time.perf_counter() - start
            labels.update((label.id, label) for label in self._canonical.values())  # pyright: ignore[reportPrivateUsage]

    SymbolicEngine.fix = timed_fix
    try:
        yield elapsed, labels
    finally:
        SymbolicEngine.fix = original


def build_system(case: Case, function: ir.Function) -> CHCSystem:
    k = function.node.k
    match case.kind:
        case "lab":
            return pre.make_system(function, k, case.m, case.n, None, FeatureFlags(), ERR_ONLY)
        case "pre":
            assert case.pre is not None
            return pre.make_system(function, k, case.m, case.n, case.pre(), FeatureFlags(), case.exit_codes)
        case _:
            raise ValueError(f"unknown kind {case.kind}")


QUERY_TYPES = ["pre_root"]


def predicate_family(name: str) -> str:
    return name.rstrip("0123456789")


def queried_predicate(clause: Clause) -> str:
    """Name of the predicate in the body of a query `P(...) ∧ φ → false`."""
    applications = [b for b in clause.body if isinstance(b, Application)]
    assert len(applications) == 1, f"a query has {len(applications)} predicates in its body"
    return applications[0].predicate.name


def query_type(name: str) -> str:
    if predicate_family(name) == "Pre":
        return "pre_root"
    raise ValueError(f"unexpected query on {name}")


def run_case(case: Case, timeout: int) -> dict[str, Any]:
    function = parse_file(str(C_FILES / f"{case.program}.c"))

    start = time.perf_counter()
    with enumeration_timer() as (enumeration, _):
        system = build_system(case, function)
    build = time.perf_counter() - start
    enum_lab = enumeration[LabEngine]

    families = Counter(predicate_family(p.name) for p in system.predicates)
    clauses = system.clauses
    queries = [c for c in clauses if c.head is False]
    query_types = Counter(query_type(queried_predicate(q)) for q in queries)

    solver = Z3Solver(SOLVERS)
    start = time.perf_counter()
    system.to_smt()
    serialize = time.perf_counter() - start

    # the solver time includes writing the system on the solver's input
    start = time.perf_counter()
    try:
        status = solver.solve(system, timeout)
    except SolverError as e:  # the solver gives up without a result
        print(f"  solver error: {e}")
        status = Status.UNKNOWN
    solve = time.perf_counter() - start

    return {
        "test": case.test,
        "program": case.program,
        "kind": case.kind,
        "m": case.m,
        "n": case.n,
        "pre": case.pre.__name__ if case.pre else None,
        "exit_codes": "+".join(sorted(e.name for e in case.exit_codes)) if case.kind == "pre" else None,
        "expected": case.expected.name,
        "status": status.name,
        "as_expected": status == case.expected,
        "enum_lab_s": enum_lab,
        "enum_total_s": enum_lab,
        "chc_build_s": build - enum_lab,
        "serialize_s": serialize,
        "solver_s": solve,
        "pre_predicates": families["Pre"],
        "predicates": sum(families.values()),
        "clauses": len(clauses),
        "queries": len(queries),
        **{f"q_{t}": query_types[t] for t in QUERY_TYPES},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="solver timeout per case, in seconds")
    parser.add_argument("--only", default=None, help="run only the cases whose test or program contains this text")
    parser.add_argument("--out", type=Path, default=None, help="output CSV file")
    args = parser.parse_args()

    cases = [c for c in CASES if args.only is None or args.only in c.test or args.only in c.program]
    out: Path = args.out or Path(f"benchmarks_{time.strftime('%Y-%m-%d_%H-%M-%S')}.csv")

    with out.open("w", newline="") as f:
        writer: csv.DictWriter[str] | None = None
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case.test} {case.program}", flush=True)
            row = run_case(case, args.timeout)
            print(
                f"  {row['status']} (expected {row['expected']}) enum {row['enum_total_s']:.2f}s "
                f"solver {row['solver_s']:.2f}s, {row['pre_predicates']} Pre predicates, {row['queries']} queries",
                flush=True,
            )
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(
                {k: "" if v is None else round(v, 4) if isinstance(v, float) else v for k, v in row.items()}
            )
            f.flush()
    print(f"results written to {out}")


if __name__ == "__main__":
    main()
