"""Runs the cases of the integration tests and measures their performance.

The cases are imported from `tests/integration`, so they stay the same as the tests (program, bounds,
precondition, nil fields, feature flags, solver, timeout). For every case it reports:
- the result given by the solver, compared with the one expected by the test;
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

Usage: uv run python scripts/bench.py [--only SUBSTRING] [--skip-slow] [--timeout SECONDS] [--out FILE.csv]
"""

import argparse
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
from tests.integration.config import SOLVERS, TestConfig, make_system, solver_available, solver_dir  # noqa: E402
from treehornx.chc.solvers.base import KILL_GRACE, resolve_binary  # noqa: E402


SUITES = [
    ("test_lab_chc::test_memory_safety", test_lab_chc.CASES),
    ("test_pre_chc::test_memory_safety_under_precondition", test_pre_chc.CASES),
    ("test_pre_chc::test_unsafe_without_precondition", test_pre_chc.WITHOUT_PRECONDITION),
]

# the timeout option of every solver, applied to its timeout in seconds
TIMEOUT_OPTION = {"z3": "-T:{}", "eldarica": "-t:{}"}


@dataclass
class Result:
    test: str
    case: str
    solver: str
    expected: str
    status: str
    """sat, unsat, unknown (solver timeout or no answer), error (exception during the generation)."""
    ok: bool
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


def solve_file(config: TestConfig, path: Path, peak_file: Path) -> tuple[str, float | None]:
    """Runs the solver of `config` on the script at `path`: the status it prints and its memory peak in MiB."""
    binary = resolve_binary(SOLVERS[config.solver].NAME, solver_dir(config.solver))
    cmd = [str(binary), str(path), TIMEOUT_OPTION[config.solver].format(config.timeout)]
    if GNU_TIME is not None:
        cmd = [GNU_TIME, "-f", "%M", "-o", str(peak_file), *cmd]
    # a session of its own, so that a timeout kills the solver and not only GNU time
    with subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=config.timeout + KILL_GRACE)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return "unknown", None
    peak = int(peak_file.read_text().split()[-1]) / 1024 if GNU_TIME is not None else None
    for line in map(str.strip, stdout.splitlines()):
        if line in ("sat", "unsat", "unknown"):
            return line, peak
        if line == "timeout":  # printed by eldarica
            return "unknown", peak
    print(f"  {binary.name} exited with code {proc.returncode}: {(stdout + stderr).strip()[:500]}")
    return "unknown", peak


def run_case(test: str, config: TestConfig) -> Result:
    """Generates, writes and solves the system of `config`, in a process of its own."""
    result = Result(test, config.test_id, config.solver, config.expected.value, "error", False)
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
            print(f"  generation failed: {type(e).__name__}: {e}")
            return result

        with path.open() as script:
            for line in script:
                result.predicates += line.startswith("(declare-fun ")
                result.clauses += line.startswith("(assert ")

        start = time.perf_counter()
        result.status, result.solver_peak_mb = solve_file(config, path, Path(tmp) / "peak")
        result.solver_s = time.perf_counter() - start
    result.ok = result.status == result.expected
    return result


def isolated(test: str, config: TestConfig) -> Result:
    """`run_case` in a fresh process: its memory peak starts from an empty interpreter."""
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as executor:
        return executor.submit(run_case, test, config).result()


def cases(only: str | None, skip_slow: bool, timeout: int | None) -> list[tuple[str, TestConfig]]:
    selected: list[tuple[str, TestConfig]] = []
    for test, params in SUITES:
        for param in params:
            config = param.values[0]
            assert isinstance(config, TestConfig)
            if only is not None and only not in test and only not in config.test_id:
                continue
            if skip_slow and any(mark.name == "slow" for mark in config.marks):
                continue
            if not solver_available(config.solver):
                print(f"skipping {config.test_id}: {SOLVERS[config.solver].NAME} not found")
                continue
            selected.append((test, config if timeout is None else replace(config, timeout=timeout)))
    return selected


COLUMNS = [
    ("solver", "{:<8}"),
    ("status", "{:<7}"),
    ("ok", "{!s:<5}"),
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default=None, help="run only the cases whose test or id contains this text")
    parser.add_argument("--skip-slow", action="store_true", help="skip the cases marked slow in the tests")
    parser.add_argument("--timeout", type=int, default=None, help="solver timeout in seconds, instead of the test's")
    parser.add_argument("--out", type=Path, default=None, help="also write the results to this CSV file")
    args = parser.parse_args()

    selected = cases(args.only, args.skip_slow, args.timeout)
    results: list[Result] = []
    case_width = max((len(config.test_id) for _, config in selected), default=4)
    print(header(case_width), flush=True)
    for test, config in selected:
        result = isolated(test, config)
        results.append(result)
        print(row(result, case_width), flush=True)

    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} as expected", end="")
    print(f", unexpected: {', '.join(f'{r.case} ({r.status})' for r in failed)}" if failed else "")

    if args.out is not None:
        with args.out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(results[0])) if results else [])
            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        k: "" if v is None else round(v, 4) if isinstance(v, float) else v
                        for k, v in asdict(result).items()
                    }
                )
        print(f"results written to {args.out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
