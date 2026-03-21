from __future__ import annotations

from typing import Annotated

import typer

app = typer.Typer(help="TreehornX report CLI.")


@app.command("compile")
def compile_cmd() -> None:
    raise NotImplementedError("compile command logic is not implemented yet")


@app.command("verify")
def verify_cmd(
    function: Annotated[str | None, typer.Option("--function", "-f")] = None,
    n: Annotated[int | None, typer.Option("-n")] = None,
    m: Annotated[int | None, typer.Option("-m")] = None,
    c: Annotated[int | None, typer.Option("-c")] = None,
    partially_correct: Annotated[bool, typer.Option("--partially-correct")] = False,
    check_sat: Annotated[bool, typer.Option("--check-sat")] = False,
    z3: Annotated[bool, typer.Option("--z3")] = False,
    golem: Annotated[bool, typer.Option("--golem")] = False,
    eldarica: Annotated[bool, typer.Option("--eldarica")] = False,
    full_dep_graph: Annotated[bool, typer.Option("--full-dep-graph")] = False,
    compressed_dep_graph: Annotated[bool, typer.Option("--compressed-dep-graph")] = False,
    internal_step_graph: Annotated[bool, typer.Option("--internal-step-graph")] = False,
) -> None:
    _ = (
        function,
        n,
        m,
        c,
        partially_correct,
        check_sat,
        z3,
        golem,
        eldarica,
        full_dep_graph,
        compressed_dep_graph,
        internal_step_graph,
    )
    raise NotImplementedError("verify command logic is not implemented yet")

def main() -> None:
    app()


if __name__ == "__main__":
    main()
