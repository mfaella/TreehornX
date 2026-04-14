from typing import Iterable

import pydot
from humanfriendly import format_timespan

from treehornx.chc.core import ExitCodeKind
from treehornx.report.visualization import DependencyGraphBuilder, DependencyGraphKind
from treehornx.ux.tui import console, critical, fail, info, progress, success, warning
from treehornx.ux.utils import take_time


def display_verify_cmd_option_messages(
    function_name: str | None,
    root_name: str | None,
    n: int | None,
    m: int | None,
    c: int | None,
    partial_correctness: bool,
    check_sat: bool,
    interactive_check_sat: bool,
    z3: bool,
    golem: bool,
    eldarica: bool,
) -> None:
    if function_name is None:
        info("No function specified, verifying the first function.")
    if root_name is None:
        info("No root specified, using default value of 'root'.")
        root_name = "root"
    if n is None:
        info("No value specified for n, using default value of 128.")
    if m is None:
        info("No value specified for m, using default value of 0.")
    if c is None and not partial_correctness:
        info("No value specified for c, using default value of 32.")
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


def display_generation_results(
    trivially_sat_exit_codes: Iterable[ExitCodeKind],
    non_trivially_sat_exit_codes: Iterable[ExitCodeKind],
) -> None:
    for exit_code in trivially_sat_exit_codes:
        success(f"{exit_code.name} is trivially satisfiable, the function is correct with respect to {exit_code.name}.")
    for exit_code in non_trivially_sat_exit_codes:
        fail(
            f"{exit_code.name} is not trivially satisfiable, further analysis is needed to determine correctness with respect to {exit_code.name}."
        )


def render_dependency_graph(graph_builder: DependencyGraphBuilder, kind: DependencyGraphKind):
    kind_name = kind.value.replace("_", " ")

    def render() -> pydot.Dot:
        g = graph_builder.dependency_graph(kind)
        file_name = f"{graph_builder.function.name}_{kind.value}_dep_graph"
        g.write(f"{file_name}.svg", format="svg")
        return g

    _, elapsed_time = progress(f"Rendering {kind_name} dependency graph", lambda _: take_time(render))
    console.print(f"{kind_name.title()} dependency graph rendered in {format_timespan(elapsed_time)}.")
