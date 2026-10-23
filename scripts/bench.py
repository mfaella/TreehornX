"""Runs the cases of the integration tests and measures their performance.

The cases are imported from `tests/integration`, so they stay the same as the tests (program, bounds,
precondition, nil fields, feature flags, solver, timeout). For every case it reports:
- the result given by the solver, compared with the one expected by the test;
- the solver deciding it (`solver`: for the portfolio the racer that won, `golem-<engine>` for golem run with an
  engine; empty when no solver decides);
- the generation time: parsing, enumeration and CHC construction (`gen_s`), then writing the SMT-LIB script,
  which includes the lazy clause cleaning (`write_s`);
- the solver time, on the script already written;
- the memory peak (resident set size) of the generation and of the solver, and the memory the process already
  used before the generation (`base_mb`: the interpreter and the imports, included in `gen_peak_mb`);
- the number of predicates and of clauses in the script given to the solver.

Every case runs in its own process, so that its memory peak does not include the previous cases. The peaks are
read from /proc (VmHWM) and from GNU time (`/usr/bin/time`) for the solver, not from getrusage: on Linux its
maxrss carries the peak of a process over exec, so a process forked from the interpreter and running the
solver would be charged with the interpreter's memory. Without GNU time the solver peak is left empty.

--save-csv and --save-txt also write the rows of the table as they come, as CSV and as the printed table, in
`bench_<timestamp>.csv` / `.txt` in the current directory; --out writes the CSV in a file of choice.

Usage: uv run python scripts/bench.py [--only SUBSTRING] [--skip-slow] [--timeout SECONDS] [--solver NAME]
       [--save-csv] [--save-txt] [--out FILE.csv]
"""

import argparse
import contextlib
import csv
import multiprocessing
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.integration import test_lab_chc, test_pre_chc  # noqa: E402
from tests.integration.config import (  # noqa: E402
    SOLVERS,
    SolverName,
    TestConfig,
    make_system,
    missing_binaries,
    solver_available,
    solver_dir,
)
from treehornx.chc.solvers import Outcome, PortfolioSolver, ProcessSolver, SolverError, Status  # noqa: E402
from treehornx.chc.solvers.base import parse_status, race_on_file  # noqa: E402


SUITES = [
    ("test_lab_chc::test_memory_safety", test_lab_chc.CASES),
    ("test_pre_chc::test_memory_safety_under_precondition", test_pre_chc.CASES),
    ("test_pre_chc::test_unsafe_without_precondition", test_pre_chc.WITHOUT_PRECONDITION),
]


@dataclass
class Result:
    test: str
    case: str
    expected: str
    status: str
    """sat, unsat, unknown (solver timeout or no answer), error (exception during the generation)."""
    ok: bool
    solver: str | None = None
    """The solver giving sat/unsat, None when no solver decides."""
    gen_s: float = 0.0
    write_s: float = 0.0
    solver_s: float = 0.0
    base_mb: float = 0.0
    gen_peak_mb: float = 0.0
    solver_peak_mb: float | None = None
    predicates: int = 0
    clauses: int = 0


def proc_status_mb(field: str) -> float:
    """The field `field` (VmRSS, VmHWM) of /proc/self/status in MiB."""
    with open("/proc/self/status") as status:
        for line in status:
            if line.startswith(f"{field}:"):
                return int(line.split()[1]) / 1024
    raise KeyError(field)


GNU_TIME = shutil.which("time")


def solve_file(config: TestConfig, path: Path, peak_file: Path) -> tuple[Outcome, float | None]:
    """Runs the solver of `config` on the script at `path`: the outcome and the memory peak of the solver in MiB.

    The portfolio races its solvers as `PortfolioSolver.solve` does, its memory peak is not measured."""
    solver = SOLVERS[config.solver](solver_dir(config.solver))
    if isinstance(solver, PortfolioSolver):
        try:
            return race_on_file(solver.solvers, path, config.timeout), None
        except SolverError as e:
            print(f"  {e}"[:500], file=sys.stderr)
            return Outcome(Status.UNKNOWN), None
    assert isinstance(solver, ProcessSolver)
    status, peak = solve_process(solver, config.timeout, path, peak_file)
    if status is Status.UNKNOWN:
        return Outcome(status), peak
    return Outcome(status, solver, tuple(solver.file_command(path, config.timeout))), peak


def solve_process(solver: ProcessSolver, timeout: int, path: Path, peak_file: Path) -> tuple[Status, float | None]:
    cmd = solver.file_command(path, timeout)
    if GNU_TIME is not None:
        cmd = [GNU_TIME, "-f", "%M", "-o", str(peak_file), *cmd]
    # a session of its own, so that a timeout kills the solver and not only GNU time
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=solver.kill_timeout(timeout))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return Status.UNKNOWN, None
    # GNU time does not write the peak of a process killed by a signal
    peak = int(peak_file.read_text().split()[-1]) / 1024 if GNU_TIME is not None and peak_file.exists() else None
    try:
        return parse_status(solver.file_command(path, timeout), proc.returncode, stdout, stderr), peak
    except SolverError as e:
        print(f"  {str(e)[:500]}", file=sys.stderr)
        return Status.UNKNOWN, peak


def run_case(test: str, config: TestConfig) -> Result:
    """Generates, writes and solves the system of `config`, in a process of its own."""
    result = Result(test, config.test_id, config.expected.value, "error", False)
    with tempfile.TemporaryDirectory(prefix="bench-") as tmp:
        path = Path(tmp) / f"{config.test_id}.smt2"
        result.base_mb = proc_status_mb("VmRSS")
        try:
            start = time.perf_counter()
            system = make_system(config)
            result.gen_s = time.perf_counter() - start

            start = time.perf_counter()
            with path.open("w") as out:
                system.write(out)
            result.write_s = time.perf_counter() - start
            result.gen_peak_mb = proc_status_mb("VmHWM")
            del system
        except Exception as e:
            print(f"  generation failed: {type(e).__name__}: {e}", file=sys.stderr)
            return result

        with path.open() as script:
            for line in script:
                result.predicates += line.startswith("(declare-fun ")
                result.clauses += line.startswith("(assert ")

        start = time.perf_counter()
        outcome, result.solver_peak_mb = solve_file(config, path, Path(tmp) / "peak")
        result.solver_s = time.perf_counter() - start
        result.status = outcome.status.value
        if outcome.solver is not None:
            result.solver = outcome.solver.label
    result.ok = result.status == result.expected
    return result


def isolated(test: str, config: TestConfig) -> Result:
    """`run_case` in a fresh process: its memory peak starts from an empty interpreter."""
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as executor:
        return executor.submit(run_case, test, config).result()


def cases(
    only: str | None, skip_slow: bool, timeout: int | None, solver: SolverName | None
) -> list[tuple[str, TestConfig]]:
    selected: list[tuple[str, TestConfig]] = []
    for test, params in SUITES:
        for param in params:
            config = param.values[0]
            assert isinstance(config, TestConfig)
            if only is not None and only not in test and only not in config.test_id:
                continue
            if skip_slow and any(mark.name == "slow" for mark in config.marks):
                continue
            if solver is not None:
                config = replace(config, solver=solver)
            if not solver_available(config.solver):
                print(
                    f"skipping {config.test_id}: {', '.join(missing_binaries(config.solver))} not found",
                    file=sys.stderr,
                )
                continue
            selected.append((test, config if timeout is None else replace(config, timeout=timeout)))
    return selected


COLUMNS = [
    ("status", "{:<7}"),
    ("ok", "{!s:<5}"),
    ("solver", "{:<13}"),
    ("gen_s", "{:>9.2f}"),
    ("write_s", "{:>8.2f}"),
    ("solver_s", "{:>9.2f}"),
    ("base_mb", "{:>8.1f}"),
    ("gen_peak_mb", "{:>11.1f}"),
    ("solver_peak_mb", "{:>14.1f}"),
    ("predicates", "{:>10}"),
    ("clauses", "{:>8}"),
]


def header(case_width: int) -> str:
    names = [name.ljust(len(fmt.format(0))) if "<" in fmt else name.rjust(len(fmt.format(0))) for name, fmt in COLUMNS]
    return " ".join(["case".ljust(case_width), *names])


def row(result: Result, case_width: int) -> str:
    values = asdict(result)
    cells = [" " * len(fmt.format(0)) if values[name] is None else fmt.format(values[name]) for name, fmt in COLUMNS]
    return " ".join([result.case.ljust(case_width), *cells])


FIELDS = ["case", *(name for name, _ in COLUMNS)]


def csv_row(result: Result) -> dict[str, object]:
    """The cells of the row of `result` in the table."""
    values = asdict(result)
    cells = {name: "" if values[name] is None else fmt.format(values[name]).strip() for name, fmt in COLUMNS}
    return {"case": result.case, **cells}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default=None, help="run only the cases whose test or id contains this text")
    parser.add_argument("--skip-slow", action="store_true", help="skip the cases marked slow in the tests")
    parser.add_argument("--timeout", type=int, default=None, help="solver timeout in seconds, instead of the test's")
    parser.add_argument(
        "--solver", choices=list(SOLVERS), default=None, help="solver of every case, instead of the test's"
    )
    parser.add_argument("--save-csv", action="store_true", help="also write the results to bench_<timestamp>.csv")
    parser.add_argument("--save-txt", action="store_true", help="also write the output to bench_<timestamp>.txt")
    parser.add_argument("--out", type=Path, default=None, help="also write the results to this CSV file")
    args = parser.parse_args()

    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    csv_paths: list[Path] = [
        *([Path(f"bench_{stamp}.csv")] if args.save_csv else []),
        *([args.out] if args.out is not None else []),
    ]
    txt_path = Path(f"bench_{stamp}.txt") if args.save_txt else None

    with contextlib.ExitStack() as stack:
        csv_writers = [
            csv.DictWriter(stack.enter_context(path.open("w", newline="")), fieldnames=FIELDS) for path in csv_paths
        ]
        txt = stack.enter_context(txt_path.open("w")) if txt_path is not None else None

        def output(line: str) -> None:
            """Prints `line` and writes it in the text file, flushed so that a long run can be followed."""
            print(line, flush=True)
            if txt is not None:
                txt.write(line + "\n")
                txt.flush()

        selected = cases(args.only, args.skip_slow, args.timeout, args.solver)
        results: list[Result] = []
        case_width = max((len(config.test_id) for _, config in selected), default=4)
        output(header(case_width))
        for writer in csv_writers:
            writer.writeheader()
        for test, config in selected:
            result = isolated(test, config)
            results.append(result)
            output(row(result, case_width))
            for writer in csv_writers:
                writer.writerow(csv_row(result))

        failed = [r for r in results if not r.ok]
        summary = f"{len(results) - len(failed)}/{len(results)} as expected"
        if failed:
            summary += f", unexpected: {', '.join(f'{r.case} ({r.status})' for r in failed)}"
        output(f"\n{summary}")
    for path in [*csv_paths, *([txt_path] if txt_path is not None else [])]:
        print(f"results written to {path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
