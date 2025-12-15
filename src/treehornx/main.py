import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from z3 import Solver

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
    for exit_code in (ExitCodeKind.ERR, ExitCodeKind.OOM, ExitCodeKind.LABEL_OVERFLOW):
        buffer = io.StringIO()
        smt2file_builder.dump(buffer, exit_code)
        solver = Solver()
        # with open(f"{file_name}_{exit_code.name}.smt2", "w") as f:
        #     print(buffer.getvalue(), file=f)
        # print(buffer.getvalue())
        solver.from_string(buffer.getvalue())
        res = solver.check()
        print(f"Function {function.name} with exit code {exit_code.name}: \t {res}")


if __name__ == "__main__":
    main(sys.argv[1:])
