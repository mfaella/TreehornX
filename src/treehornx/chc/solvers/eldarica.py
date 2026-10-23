from pathlib import Path

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import ProcessSolver, Status, run_piped


class EldaricaSolver(ProcessSolver):
    """Eldarica, through `eld -in`."""

    NAME = "eld"

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        cmd = [str(self.binary), "-in"]
        if timeout is not None:
            cmd.append(f"-t:{timeout}")
        return run_piped(cmd, system, timeout)

    @override
    def file_command(self, path: Path, timeout: int | None) -> list[str]:
        timeout_args = [] if timeout is None else [f"-t:{timeout}"]
        return [str(self.binary), *timeout_args, str(path)]
