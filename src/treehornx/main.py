from __future__ import annotations

import re
import time
from collections import defaultdict
from filecmp import DEFAULT_IGNORES
from itertools import count
from operator import ge
from typing import Annotated, Any, Callable, DefaultDict, Iterable

import pydot
import typer
from codetiming import Timer
from func_timeout import FunctionTimedOut, func_timeout
from humanfriendly import format_timespan
from rich.console import Console

import treehornx.report.serialization as sr
import treehornx.validation.dependency_graph as vdp
from treehornx.chc.smt2 import ExitCodeKind, SMT2FileBuilder
from treehornx.enum_labels.core.Event import ERR, LOF, OOM
from treehornx.enum_labels.FixPointEnumLabelGenerator import FixPointEnumLabelGenerator
from treehornx.enum_labels.LabelDB import LabelDB
from treehornx.enum_labels.PairDB import PairDB
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.parser.CParser import CParser
from treehornx.report.format import label_to_json
from treehornx.report.visualization import DependencyGraphBuilder, DependencyGraphKind

app = typer.Typer(help="TreehornX CLI.")
console = Console()


def warning(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[black on yellow]WARNING![/black on yellow] {message}")


def critical(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[black on #ff8c00]CRITICAL![/black on #ff8c00] {message}")


def info(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[blue]INFO:[/blue] {message}")


def error(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[black on red]ERROR![/black on red] {message}")


def fail(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[red]FAIL![/red] {message}")


def success(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[green]SUCCESS![/green] {message}")


@app.command("compile")
def compile_cmd(
    input_file: Annotated[str, typer.Argument(help="Path to the input file containing the function to verify")],
    function: Annotated[str | None, typer.Option("--function", "-f")] = None,
) -> None:
    function = parse_function(input_file, function)
    if function is None:
        error(f"Function {function} not found in {input_file}.")
        typer.Exit(1)
    else:
        output_file = f"{function.name}.thx"
        with open(output_file, "w") as f:
            f.write(str(function))
        console.print(f"Function {function.name} compiled to {output_file}.")


DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_C = 32


def take_time[T](func: Callable[[], T]) -> tuple[T, float]:
    start = time.time()
    result = func()
    end = time.time()
    return result, end - start


def parse_function(file_name: str, function_name: str | None = None) -> Function | None:
    parser = CParser()
    if function_name is None:
        return next(iter(parser.parse_file(file_name)), None)
    else:
        return next(
            (f for f in parser.parse_file(file_name) if f.name == function_name),
            None,
        )


def generate_labels(generator: FixPointEnumLabelGenerator, timeout: int | None = None) -> bool:
    with console.status("Generating labels"):
        time = None
        if timeout is None:
            _, time = take_time(generator.generate)
        else:
            try:
                _, time = take_time(lambda: func_timeout(timeout, generator.generate))  # type: ignore
            except FunctionTimedOut:
                warning(f"Label generation timed out after {timeout} seconds.")
    generation_completed = time is not None
    if generation_completed:
        console.print(f"All labels have been generated in {format_timespan(time)}.")
    console.print(f"Generated labels: {len(generator.labels)}.")
    longest_length = max((len(lab) for lab in generator.labels), default=0)
    console.print(f"Longest label length: {longest_length}.")
    return generation_completed


def render_dependency_graph(graph_builder: DependencyGraphBuilder, kind: DependencyGraphKind):
    kind_name = kind.value.replace("_", " ")
    with console.status(f"Rendering {kind_name} dependency graph"):

        def render() -> pydot.Dot:
            g = graph_builder.dependency_graph(kind)
            file_name = f"{graph_builder.function.name}_{kind.value}_dep_graph"
            g.write(f"{file_name}.dot", format="dot")
            g.write(f"{file_name}.svg", format="svg")
            return g

        g, time = take_time(render)
    nodes_count = len(g.get_nodes())
    names = {node.get_name() for node in g.get_nodes()}
    assert len(names) == nodes_count, "Duplicate node names in the graph, this should not happen."
    console.print(f"{kind_name.title()} dependency graph rendered in {format_timespan(time)}.")
    console.print(f"{kind_name.title()} dependency graph contains {nodes_count} nodes.")


def handle_generation_results(
    generation_completed: bool,
    generator: FixPointEnumLabelGenerator,
    function: Function,
    root: Var,
    smt2: bool,
) -> None:
    trivially_sat: defaultdict[ExitCodeKind, bool] = defaultdict(lambda: True)

    if generation_completed:
        for lab in generator.labels:
            if ERR() in lab.frame.events:
                trivially_sat[ExitCodeKind.ERR] = False
            if OOM() in lab.frame.events:
                trivially_sat[ExitCodeKind.OOM] = False
            if LOF() in lab.frame.events:
                trivially_sat[ExitCodeKind.LABEL_OVERFLOW] = False

        exit_codes = (ExitCodeKind.ERR, ExitCodeKind.OOM, ExitCodeKind.LABEL_OVERFLOW)
        facts = {*generator.backbone_labels(), *generator.start_labels()}
        smt2builder = SMT2FileBuilder(function, root.sort.pointee, generator.labels, generator.pairs, facts)
        for exit_code in exit_codes:
            if trivially_sat[exit_code]:
                success(
                    f"{exit_code.name} is trivially satisfiable, the function is correct with respect to {exit_code.name}."
                )
        for exit_code in exit_codes:
            if not trivially_sat[exit_code]:
                fail(
                    f"{exit_code.name} is not trivially satisfiable, further analysis is needed to determine correctness with respect to {exit_code.name}."
                )
                if smt2:
                    file_name = f"{function.name}_{exit_code.name}.smt2"
                    with console.status(f"Dumping SMT2-LIB formulas to {file_name} respect to {exit_code.name}"):
                        _, time = take_time(
                            lambda: smt2builder.dump_to_file(file_name, exit_code, check_sat=True, exit=True)
                        )
                    console.print(
                        f"SMT2-LIB formulas dumped to {file_name} respect to {exit_code.name} in {format_timespan(time)}."
                    )


@app.command("verify")
def verify_cmd(
    input_file: Annotated[
        str,
        typer.Argument(
            exists=True,  # path must exist
            file_okay=True,  # can be a file
            dir_okay=False,  # cannot be a directory
            readable=True,  # must be readable
            resolve_path=True,  # resolves to absolute path automatically)],
        ),
    ],
    function_name: Annotated[str | None, typer.Option("--function", "-f")] = None,
    root_name: Annotated[str | None, typer.Option("--root", "-r")] = None,
    n: Annotated[int | None, typer.Option("-n")] = None,
    m: Annotated[int | None, typer.Option("-m")] = None,
    c: Annotated[int | None, typer.Option("-c")] = None,
    generation_timeout: Annotated[int | None, typer.Option("--generation-timeout")] = None,
    partial_correctness: Annotated[bool, typer.Option("--partial-correctness")] = False,
    smt2: Annotated[bool, typer.Option("--smt2")] = False,
    check_sat: Annotated[bool, typer.Option("--check-sat")] = False,
    interactive_check_sat: Annotated[bool, typer.Option("--interactive-check-sat")] = False,
    z3: Annotated[bool, typer.Option("--z3")] = False,
    golem: Annotated[bool, typer.Option("--golem")] = False,
    eldarica: Annotated[bool, typer.Option("--eldarica")] = False,
    full_dep_graph: Annotated[bool, typer.Option("--fdg", "--full-dep-graph")] = False,
    compressed_dep_graph: Annotated[bool, typer.Option("--cdg", "--compressed-dep-graph")] = False,
    internal_dependency_graph: Annotated[bool, typer.Option("--idg", "--internal-dep-graph")] = False,
    compressed_internal_dependency_graph: Annotated[
        bool, typer.Option("--cidg", "--compressed-internal-dep-graph")
    ] = False,
    serialize: Annotated[bool, typer.Option("--serialize")] = False,
) -> None:
    if function_name is None:
        info("No function specified, verifying the first function.")
    if root_name is None:
        info("No root specified, using default value of 'root'.")
        root_name = "root"
    if n is None:
        info("No value for n specified, using default value of 128.")
        n = DEFAULT_N
    if m is None:
        info("No value for m specified, using default value of 0.")
        m = DEFAULT_M
    if c is None and not partial_correctness:
        info("No value for c specified, using default value of 32.")
        c = DEFAULT_C
    if partial_correctness and c is not None:
        warning("Value for c specified, but --partial-correctness is anabled and c is ignored.")
    if check_sat:
        critical("--check-sat not supported, it is ignored")
    if check_sat and not any((z3, golem, eldarica)):
        info("using z3 by default.")
    if interactive_check_sat and check_sat:
        warning("Both --interactive-check-sat and --check-sat specified, using interactive check-sat.")
    if interactive_check_sat:
        critical("--interactive-check-sat not supported, it is ignored")
    if len([solver for solver in [z3, golem, eldarica] if solver]) > 1:
        warning("Multiple solvers specified, using z3 by default.")

    function = parse_function(input_file, function_name)
    if function is None:
        error(f"Function {function_name} not found in {input_file}.")
        typer.Exit(1)
        return  # useless but mypy/pyright doesn't know that typer.Exit exits the program

    root = next((var for var in function.vars if var.name == root_name), None)
    if root is None:
        error(f"Root variable {root_name} not found in function {function.name}.")
        typer.Exit(1)
        return  # useless but mypy/pyright doesn't know that typer.Exit exits the program

    generator = FixPointEnumLabelGenerator(function, root, m, n, c)
    generation_completed = generate_labels(generator, generation_timeout)

    handle_generation_results(generation_completed, generator, function, root, smt2)

    # old_labels, old_pairs = sr.deserialize(f"{function.name}_serialized.pkl")
    # old_labels_set = set(old_labels)
    # labels_set = set(generator.labels)
    # print(f"len(old_labels) = {len(old_labels)}")
    # print(f"len(labels_set) = {len(labels_set)}")
    # print(f"len(generator.labels) = {len(generator.labels)}")
    # print(set(generator.labels) - set(old_labels))

    if serialize:
        file_name = f"{function.name}_serialized.pkl"
        with console.status(f"Serializing labels and pairs to {file_name}"):
            _, time = take_time(lambda: sr.serialize(file_name, generator.labels, generator.pairs))
        console.print(f"Labels and pairs serialized to {file_name} in {format_timespan(time)}.")

    graph_builder = DependencyGraphBuilder(function, generator.labels, generator.pairs)
    if full_dep_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.FULL)
    if compressed_dep_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.COMPRESSED)
    if internal_dependency_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.INTERNAL)
    if compressed_internal_dependency_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.COMPRESSED_INTERNAL)

    typer.Exit(0)


def validate_uninterrupted_generation(labels: LabelDB, pairs: PairDB):
    with console.status("Building dependency graph"):
        graph = vdp.build_dependency_graph(labels, pairs)
    with console.status("Validating uninterrupted generation"):
        validation = vdp.validate_label_end_nodes(graph)
    if validation:
        success("Validation of uninterrupted generation succeeded.")
    else:
        fail("Validation of uninterrupted generation failed.")


@app.command("validate")
def validate_cmd(
    labels_file: Annotated[
        str,
        typer.Argument(
            exists=True,  # path must exist
            file_okay=True,  # can be a file
            dir_okay=False,  # cannot be a directory
            readable=True,  # must be readable
            resolve_path=True,  # resolves to absolute path automatically)],
        ),
    ],
    diff: Annotated[
        str | None,
        typer.Option(
            "--diff",
            exists=True,  # path must exist
            file_okay=True,  # can be a file
            dir_okay=False,  # cannot be a directory
            readable=True,  # must be readable
            resolve_path=True,  # resolves to absolute path automatically)],
        ),
    ] = None,
    uninterrupted_generation: Annotated[bool, typer.Option("--uninterrupted-generation")] = False,
) -> None:
    with console.status(f"Deserializing labels and pairs from {labels_file}"):
        labels, pairs = sr.deserialize(labels_file)
    if uninterrupted_generation:
        validate_uninterrupted_generation(labels, pairs)

    if diff is not None:
        with console.status("Computing diff"):
            labels2, pairs2 = sr.deserialize(diff)
            # print(f"len(labels) = {len(labels)}")
            # print(f"len(labels2) = {len(labels2)}")
            # graph1 = vdp.build_dependency_graph(labels, pairs)
            # graph2 = vdp.build_dependency_graph(labels2, pairs2)
            # nodes1 = set(graph1.nodes)
            # console.print(f"Graph 1 has {len(nodes1)} nodes.")
            # nodes2 = set(graph2.nodes)
            # console.print(f"Graph 2 has {len(nodes2)} nodes.")
            # common_nodes = nodes1.intersection(nodes2)
            removed_nodes = set(labels) - set(labels2)
            added_nodes = set(labels2) - set(labels)
        console.print("Diff computed")
        # for node in set(labels) - set(graph1.nodes):
        #     console.print(f"[blue]   Lab{labels.id(node)} : {label_to_json(node)}[/blue]")
        for node in removed_nodes:
            console.print(f"[red] - Lab{labels.id(node)} : {label_to_json(node)}[/red]")
        for node in added_nodes:
            console.print(f"[green] + Lab{labels2.id(node)} : {label_to_json(node)}[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
