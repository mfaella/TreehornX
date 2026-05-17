from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, TypeAlias

import typer
from rich.console import Console

from treehornx.chc.SDTAContext import SDTAContext
from treehornx.chc.SDTAContext import (
    avl_ctx,
    avl_strict_ctx,
    bst_ctx,
    bst_strict_ctx,
    rb_ctx,
    rb_strict_ctx,
    sll_sorted_ctx,
    sll_sorted_strict_ctx,
)
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

PostType: TypeAlias = Literal["tree", "bst", "bst_strict", "sll_sorted", "sll_sorted_strict", "avl", "avl_strict", "rb", "rb_strict"]

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
    pre: Annotated[
        Literal["bst", "bst_strict", "sll_sorted", "sll_sorted_strict", "avl", "avl_strict", "rb", "rb_strict"] | None,
        typer.Option("--pre"),
    ] = None,
    post: Annotated[PostType|None, typer.Option("--post")] = None,
    produce_csv: Annotated[bool, typer.Option("--csv")] = False,
    produce_json: Annotated[bool, typer.Option("--json")] = False,
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

    pre_map: dict[str, SDTAContext] = {
        "bst": bst_ctx(),
        "bst_strict": bst_strict_ctx(),
        "sll_sorted": sll_sorted_ctx(),
        "sll_sorted_strict": sll_sorted_strict_ctx(),
        "avl": avl_ctx(),
        "avl_strict": avl_strict_ctx(),
        "rb": rb_ctx(),
        "rb_strict": rb_strict_ctx(),
    }
    pre_ctx = pre_map[pre] if pre else None

    post_map: dict[str, SDTAContext | bool] = {
        "tree": True,
        "bst": bst_ctx(),
        "bst_strict": bst_strict_ctx(),
        "sll_sorted": sll_sorted_ctx(),
        "sll_sorted_strict": sll_sorted_strict_ctx(),
        "avl": avl_ctx(),
        "avl_strict": avl_strict_ctx(),
        "rb": rb_ctx(),
        "rb_strict": rb_strict_ctx(),
    }
    post_ctx = post_map[post] if post else None

    if pre_ctx is None:
        trees = handle_label_generation(function, root, n, m, c)
    else:
        trees = handle_label_generation(function, root, n, m, c, pre_ctx.label_filter, pre_ctx.pair_filter)
    trivially_sat = compute_trivially_sat(trees)

    display_generation_results(
        (k for k, v in trivially_sat.items() if v),
        (k for k, v in trivially_sat.items() if not v),
    )
    if smt2:
        exit_codes = [k for k, v in trivially_sat.items() if not v]
        assert pre_ctx
        assert post_ctx
        handle_smt2_scripts_creation(function, root, trees, exit_codes, pre_ctx, post_ctx)

    graph_builder = DependencyGraphBuilder(function, trees)
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
