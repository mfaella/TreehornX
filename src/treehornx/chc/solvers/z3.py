from pathlib import Path

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import CHCSolver, Status, resolve_binary, run_piped


class Z3Solver(CHCSolver):
    """Spacer, through `z3 -in`."""

    NAME = "z3"

    def __init__(self, solvers_dir: Path | None = None) -> None:
        self.binary = resolve_binary(self.NAME, solvers_dir)

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        cmd = [str(self.binary), "-in"]
        if timeout is not None:
            cmd.append(f"-T:{timeout}")
        return run_piped(cmd, system, timeout)
