"""Solves the CHC system of one check query by query: every copy holds all the rules of the system and one of its
queries, and the copies are solved one at a time with z3.

The whole system is sat iff every copy is sat (sat = safe), so an unsat copy is a violation. Splitting helps when
z3 does not solve the whole system: most copies are solved in seconds and the hard ones can be retried alone.

The system is built and the copies are written in a child process, which exits before z3 starts, so the memory of
the system is free while the solver runs. Copies already in the output directory are not written again; a copy is
deleted after it is solved, unless --keep is given. One line per copy is appended to the results file:
`query_NNN status seconds peak_KB`, where status is sat, unsat, unknown, timeout, memout (z3 exited with 101 at
--memory) or error.

Usage: uv run python scripts/solve_by_query.py FILE.c --check POST --pre avl --post avl -m 1 --clean-clause
           [--out-dir DIR] [--first I] [--last J] [--timeout S] [--memory MB] [--no-global] [--z3 PATH] [--keep]
"""

import argparse
import itertools
import multiprocessing
import os
import subprocess
import time
from pathlib import Path
from typing import Iterable

from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.system import build_lab, to_system
from treehornx.chc.Post import post_clauses
from treehornx.chc.smt.sexpr import CHCSystem, Clause, Predicate
from treehornx.chc.TreeShape import tree_shape_clauses
from treehornx.chc.TreeShape.system import tree_shape_from_lab
from treehornx.main import POST, POST_CHECK, PRE, TREE_SHAPE, memory_clauses
from treehornx.parser import parse_file


ROOT = Path(__file__).parent.parent
Z3 = ROOT / "tests" / "integration" / "solvers" / "z3"
CHECKS = [*(code.name for code in ExitCodeKind), TREE_SHAPE, POST_CHECK]
MEMOUT = 101
"""The exit status of z3 when it reaches memory_max_size."""


def check_clauses(args: argparse.Namespace) -> tuple[list[Predicate], Iterable[Clause]]:
    """The predicates and clauses of the system of `args.check`, as `treehornx verify` builds them."""
    function = parse_file(args.file)
    pre_ctx = PRE[args.pre]() if args.pre else None
    lab = build_lab(function, function.node.k, args.m, args.n)
    if args.check == TREE_SHAPE:
        return tree_shape_clauses(function, tree_shape_from_lab(lab), args.m, args.n, pre_ctx)
    if args.check == POST_CHECK:
        if not args.post:
            raise SystemExit("--check POST needs --post")
        return post_clauses(function, tree_shape_from_lab(lab), args.m, args.n, pre_ctx, POST[args.post]())
    return memory_clauses(function, lab, args.m, args.n, ExitCodeKind[args.check], pre_ctx)


def query_path(out_dir: Path, i: int) -> Path:
    return out_dir / f"query_{i:03d}.smt2"


def dump(args: argparse.Namespace, count_file: Path) -> None:
    """Writes the copies of the queries in [args.first, args.last] that are not in `args.out_dir` yet, and the number
    of queries of the system in `count_file`."""
    system = to_system(*check_clauses(args), args.clean_clause)
    rules = [c for c in system.clauses if c.head is not False]
    queries = [c for c in system.clauses if c.head is False]
    print(f"{len(rules)} rules, {len(queries)} queries", flush=True)
    count_file.write_text(str(len(queries)))
    last = len(queries) - 1 if args.last is None else min(args.last, len(queries) - 1)
    for i in range(args.first, last + 1):
        path = query_path(args.out_dir, i)
        if path.exists():
            continue
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            CHCSystem(system.predicates, [*rules, queries[i]], system.transform).write(f)
        tmp.rename(path)


def solve(z3: Path, path: Path, timeout: int, memory: int, global_guidance: bool) -> tuple[str, float, int]:
    """The status of z3 on `path`, its wall-clock time and its peak resident memory in KB."""
    cmd = [str(z3), f"-T:{timeout}", f"memory_max_size={memory}"]
    if global_guidance:
        cmd.append("fp.spacer.global=true")
    out = path.with_suffix(".out")
    start = time.monotonic()
    with open(out, "w") as f:
        # waited with os.wait4, not by Popen, to read the peak memory of the process
        process = subprocess.Popen([*cmd, str(path)], stdout=f, stderr=subprocess.STDOUT)
    pid, wait_status, usage = os.wait4(process.pid, os.WNOHANG)
    while pid == 0:
        if time.monotonic() - start > timeout + 60:
            process.kill()
            pid, wait_status, usage = os.wait4(process.pid, 0)
            break
        time.sleep(0.5)
        pid, wait_status, usage = os.wait4(process.pid, os.WNOHANG)
    process.returncode = os.waitstatus_to_exitcode(wait_status)
    elapsed = time.monotonic() - start
    output = out.read_text().split()
    out.unlink()
    first = output[0] if output else ""
    if first in ("sat", "unsat"):
        return first, elapsed, usage.ru_maxrss
    if process.returncode == MEMOUT:
        return "memout", elapsed, usage.ru_maxrss
    if elapsed >= timeout:
        return "timeout", elapsed, usage.ru_maxrss
    return ("unknown" if first == "unknown" else "error"), elapsed, usage.ru_maxrss


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="the C file")
    parser.add_argument("--check", choices=CHECKS, default=POST_CHECK, help="the check whose system is solved")
    parser.add_argument("--pre", choices=sorted(PRE), default=None, help="the precondition")
    parser.add_argument("--post", choices=sorted(POST), default=None, help="the postcondition (with --check POST)")
    parser.add_argument("-m", type=int, default=0, help="the number of allocations")
    parser.add_argument("-n", type=int, default=128, help="the number of frames per label")
    parser.add_argument("--clean-clause", action="store_true", help="merge the variables equated in a clause body")
    parser.add_argument("--out-dir", type=Path, default=None, help="where the copies go (default: FILE_CHECK/)")
    parser.add_argument("--results", type=Path, default=None, help="the results file (default: OUT_DIR/results.txt)")
    parser.add_argument("--first", type=int, default=0, help="the first query to solve")
    parser.add_argument("--last", type=int, default=None, help="the last query to solve (default: the last one)")
    parser.add_argument("--timeout", type=int, default=1200, help="seconds per copy")
    parser.add_argument("--memory", type=int, default=14000, help="z3 memory_max_size per copy, in MB")
    parser.add_argument("--no-global", action="store_true", help="do not pass fp.spacer.global=true to z3")
    parser.add_argument("--z3", type=Path, default=Z3, help="the z3 binary")
    parser.add_argument("--keep", action="store_true", help="keep each copy after it is solved")
    args = parser.parse_args()

    args.out_dir = args.out_dir or Path(f"{args.file.stem}_{args.check.lower()}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = args.results or args.out_dir / "results.txt"
    count_file = args.out_dir / "queries.txt"

    child = multiprocessing.get_context("fork").Process(target=dump, args=(args, count_file))
    start = time.monotonic()
    child.start()
    child.join()
    if child.exitcode != 0:
        raise SystemExit(f"the dump failed with exit status {child.exitcode}")
    print(f"dump {time.monotonic() - start:.1f} s", flush=True)

    count = int(count_file.read_text())
    last = count - 1 if args.last is None else min(args.last, count - 1)
    statuses: dict[str, list[int]] = {}
    for i in range(args.first, last + 1):
        path = query_path(args.out_dir, i)
        status, elapsed, peak = solve(args.z3, path, args.timeout, args.memory, not args.no_global)
        line = f"{path.stem} {status} {elapsed:.1f} {peak}"
        print(line, flush=True)
        with open(results, "a") as f:
            f.write(line + "\n")
        statuses.setdefault(status, []).append(i)
        if not args.keep:
            path.unlink()

    print(", ".join(f"{status}: {len(ids)}" for status, ids in sorted(statuses.items())))
    if "unsat" in statuses:
        print(f"violation: queries {statuses['unsat']} are unsat")
    elif set(statuses) == {"sat"}:
        print(f"{args.check} holds on queries {args.first}-{last}")
    else:
        open_ids = sorted(itertools.chain(*(ids for status, ids in statuses.items() if status != "sat")))
        print(f"open queries: {open_ids}")


if __name__ == "__main__":
    main()
