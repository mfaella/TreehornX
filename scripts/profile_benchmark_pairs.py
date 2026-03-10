#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from loguru import logger

from treehornx.chc.ChcGenerator import ChcGenerator
from treehornx.chc.core.dir import Down, Internal, Up
from treehornx.chc.core.event import ERR, LOF, OOM, Exit
from treehornx.chc.core.frame import Frame
from treehornx.chc.core.label import Label
from treehornx.chc.core.pair import Pair
from treehornx.chc.Stepper import StepKind
from treehornx.ir.function import Function
from treehornx.parser.CParser import CParser


def parse_function(path: Path, function_name: str) -> Function:
    parser = CParser()
    for function in parser.parse_file(str(path)):
        if function.name == function_name:
            return function
    raise ValueError(f"Function '{function_name}' not found in {path}")


def leader_created_by_internal_step(pair: Pair) -> bool:
    prev = pair.leader().frame.prev
    return prev is not None and isinstance(prev[0], Internal)


def label_created_by_internal_step(label: Label) -> bool:
    prev = label.frame.prev
    return prev is not None and isinstance(prev[0], Internal)


def leader_has_terminal_event(pair: Pair) -> bool:
    event = pair.leader().frame.event
    return isinstance(event, (ERR, OOM, LOF, Exit))


def produces_external_step(generator: ChcGenerator, pair: Pair) -> bool:
    step = generator.step(pair)
    return step is not None and step[2] == StepKind.EXTERNAL


def frame_has_terminal_event(frame: Frame) -> bool:
    return isinstance(frame.event, (ERR, OOM, LOF, Exit))


def frame_key_ignoring_indices(frame: Frame) -> tuple[object, ...]:
    return (
        frame.active,
        frame.pc,
        frame.upd,
        frame.isnil,
        frame.event,
        frame.active_child,
        frame.enum_values,
        frame.enum_fields,
        (frame.prev[0], None) if frame.prev is not None else None,
    )


def transformed_label_key(label: Label, removable_prefixes: set[Label]) -> tuple[tuple[object, ...], ...]:
    prefixes: list[Label] = []
    current: Label | None = label
    while current is not None:
        prefixes.append(current)
        current = current.origin
    prefixes.reverse()
    return tuple(frame_key_ignoring_indices(prefix.frame) for prefix in prefixes if prefix not in removable_prefixes)


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="WARNING")

    cli = argparse.ArgumentParser(
        description=(
            "Profile pair generation and report counts for leaders created by internal "
            "steps that do not produce an external step and are not ERR/OOM/LOF/Exit."
        )
    )
    cli.add_argument(
        "--benchmark",
        default="benchmarks/safe/sll_safe_insert_sorted.c",
        help="Path to the benchmark C file.",
    )
    cli.add_argument(
        "--function",
        default="sll_safe_insert_sorted",
        help="Function name to analyze.",
    )
    cli.add_argument(
        "--root",
        default="root_0",
        help="Root pointer variable name.",
    )
    cli.add_argument("--m", type=int, default=0, help="Heap branching bound (m).")
    cli.add_argument("--n", type=int, default=25, help="Label depth bound (n).")
    args = cli.parse_args()

    benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {benchmark_path}")

    function = parse_function(benchmark_path, args.function)
    root = next((v for v in function.vars if v.name == args.root), None)
    if root is None:
        available_ptrs = [v.name for v in function.vars if v.sort.is_ptr()]
        raise ValueError(
            f"Root '{args.root}' not found in function '{function.name}'. Pointer variables: {available_ptrs}"
        )

    start_time = time.perf_counter()
    generator = ChcGenerator(function, root, args.m, args.n, create_dependency_graph=False)
    generator.generate()
    elapsed_s = time.perf_counter() - start_time

    pairs = tuple(generator.db.pairs_db)
    total_pairs = len(pairs)

    filtered_pairs = sum(
        1
        for pair in pairs
        if leader_created_by_internal_step(pair)
        and not produces_external_step(generator, pair)
        and not leader_has_terminal_event(pair)
    )

    pairs_by_leader: defaultdict[Label, list[Pair]] = defaultdict(list)
    for pair in pairs:
        pairs_by_leader[pair.leader()].append(pair)

    removable_prefixes: set[Label] = set()
    for label in generator.labels_db.db:
        if not label_created_by_internal_step(label):
            continue
        if frame_has_terminal_event(label.frame):
            continue
        leader_pairs = pairs_by_leader.get(label, [])
        if not any(produces_external_step(generator, pair) for pair in leader_pairs):
            removable_prefixes.add(label)

    transformed_keys = [transformed_label_key(label, removable_prefixes) for label in generator.labels_db.db]
    equal_labels_after_removal = set(transformed_keys)
    uniqued_labels_after_removal = len(equal_labels_after_removal)

    print(f"benchmark: {benchmark_path}")
    print(f"function: {function.name}")
    print(f"root: {args.root}")
    print(f"m: {args.m}")
    print(f"n: {args.n}")
    print(f"elapsed_seconds: {elapsed_s:.3f}")
    print(f"total_pairs: {total_pairs}")
    print(f"pairs_internal_leader_no_external_not_err_oom_lof_exit: {filtered_pairs}")
    # print(f"total_labels: {len(transformed_keys)}")
    print(f"removed_frames: {len(removable_prefixes)}")
    print(f"unique_labels_after_removal_ignoring_indices: {uniqued_labels_after_removal}")
    print(f"total_labels_after_removal_ignoring_indices: {len(transformed_keys)}")
    # print(f"equal_labels_after_removal_ignoring_indices: {equal_labels_after_removal}")


if __name__ == "__main__":
    main()
