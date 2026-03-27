from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from treehornx.enum_labels import generate_labels
from treehornx.report.visualization import DependencyGraphBuilder, DependencyGraphKind
from treehornx.ux.output import display_generation_results, display_verify_cmd_option_messages, render_dependency_graph
from treehornx.ux.parsing import handle_function_parsing, handle_root_fetching
from treehornx.ux.verify import compute_trivially_sat, handle_label_generation, handle_smt2_scripts_creation


app = typer.Typer(help="TreehornX CLI.")
console = Console()


@app.command("compile")
def compile_cmd(
    input_file: Annotated[str, typer.Argument(help="Path to the input file containing the function to verify")],
    function_name: Annotated[str | None, typer.Option("--function", "-f")] = None,
) -> None:
    function = handle_function_parsing(input_file, function_name)
    if function is None:
        typer.Exit(1)
        return  # useless but mypy/pyright doesn't know that typer.Exit exits the program
    output_file = f"{function.name}.thx.ir"
    with open(output_file, "w") as f:
        f.write(str(function_name))
    console.print(f"Function {function.name} compiled to {output_file}.")


DEFAULT_N = 128
DEFAULT_M = 0
DEFAULT_C = 32


@app.command("verify")
def verify_cmd(
    input_file: Annotated[
        Path,
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
) -> None:
    display_verify_cmd_option_messages(
        function_name,
        root_name,
        n,
        m,
        c,
        partial_correctness,
        check_sat,
        interactive_check_sat,
        z3,
        golem,
        eldarica,
    )
    root_name = root_name or "root"
    n = n or DEFAULT_N
    m = m or DEFAULT_M
    c = c or (None if partial_correctness else DEFAULT_C)

    function = handle_function_parsing(str(input_file), function_name)
    if function is None:
        typer.Exit(1)
        return  # useless but mypy/pyright doesn't know that typer.Exit exits the program

    root = handle_root_fetching(function, root_name)
    if root is None:
        typer.Exit(1)
        return  # useless but mypy/pyright doesn't know that typer.Exit exits the program

    lace_over_approx = handle_label_generation(function, root, n, m, c)
    trivially_sat = compute_trivially_sat(lace_over_approx)

    display_generation_results(
        (k for k, v in trivially_sat.items() if v),
        (k for k, v in trivially_sat.items() if not v),
    )
    if smt2:
        handle_smt2_scripts_creation(function, root, lace_over_approx, [k for k, v in trivially_sat.items() if not v])

    graph_builder = DependencyGraphBuilder(function, lace_over_approx)
    if full_dep_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.FULL)
    if compressed_dep_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.COMPRESSED)
    if internal_dependency_graph:
        render_dependency_graph(graph_builder, DependencyGraphKind.INTERNAL)

    typer.Exit(0)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
