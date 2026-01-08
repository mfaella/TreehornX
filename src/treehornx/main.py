import io
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .chc.ChcGenerator import ChcGenerator
from .chc.SMT2FileBuilder import ExitCodeKind
from .ir.function import Function
from .parser.CParser import CParser


@dataclass
class KTConfigDict:
    m: int
    n: int
    function: str | None
    root: str = "root"


def parse_options(args: Iterable[str]) -> KTConfigDict:
    config = dict(((res := arg.split("="))[0], res[1]) for arg in args)
    m = int(config.get("m", 1))
    n = int(config.get("n", 20))
    root_name = config.get("root", "root_0")
    if "function" not in config:
        raise RuntimeError("function name is required, specify with 'function=<function-name>'")
    else:
        function_name = config["function"]
    return KTConfigDict(m=m, n=n, root=root_name, function=function_name)


def parse_functions(file_name: str) -> Iterable[Function]:
    parser = CParser()
    return parser.parse_file(file_name)


def solvesmt2(smt2_string: str) -> str:
    result = subprocess.run(
        "z3 -in",
        shell=True,
        input=smt2_string,
        capture_output=True,
        text=True,
        timeout=30,  # Adjust based on your needs
    )

    return result.stdout.strip()
    # if result.returncode == 0:
    #     return result.stdout.strip()
    # else:
    #     return "unknown"


def main(args: list[str]):
    file_name = args[-1]
    if not Path(file_name).exists():
        raise ValueError(f"{file_name} not found")
    config = parse_options(args[:-1])
    function = next(f for f in parse_functions(file_name))
    print(function)
    root = next(v for v in function.vars if v.name == config.root)
    chcgen = ChcGenerator(
        function,
        root,
        config.m,
        config.n,
    )
    smt2file_builder = chcgen.generate()
    output_path = Path("report")
    output_path.mkdir(parents=True, exist_ok=True)
    with open(f"report/{function.name}.dot", "w") as f:
        f.write(chcgen.dependency_graph.source)
    with open(f"report/{function.name}_LABELS.json", "w") as labels_file:
        chcgen.labels_db.dump(labels_file)
    for exit_code in (ExitCodeKind.ERR, ExitCodeKind.OOM, ExitCodeKind.LABEL_OVERFLOW):
        if smt2file_builder.is_trivially_sat_for(exit_code):
            result = "sat"
        else:
            buffer = io.StringIO()
            with open(f"{function.name}_{exit_code.name}.smt2", "w") as f:
                smt2file_builder.dump(buffer, exit_code, check_sat=True)
                smt2file_builder.dump(f, exit_code, check_sat=True)
            result = solvesmt2(buffer.getvalue())
        print(f"Function {function.name} with exit code {exit_code.name}: \t {result}")


if __name__ == "__main__":
    main(sys.argv[1:])
