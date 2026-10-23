from pathlib import Path

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import ProcessSolver, Status, run_piped


class Z3Solver(ProcessSolver):
    """Spacer, through `z3 -in`."""

    NAME = "z3"

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        cmd = [str(self.binary), "-in"]
        if timeout is not None:
            cmd.append(f"-T:{timeout}")
        return run_piped(cmd, system, timeout)

    @override
    def file_command(self, path: Path, timeout: int | None) -> list[str]:
        timeout_args = [] if timeout is None else [f"-T:{timeout}"]
        return [str(self.binary), *timeout_args, str(path)]
