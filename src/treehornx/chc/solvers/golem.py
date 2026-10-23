from pathlib import Path

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import ProcessSolver, Status, run_on_file


class GolemSolver(ProcessSolver):
    """Golem, on the system written to a file: it does not read its standard input nor take a timeout, so it is
    killed when the timeout expires."""

    NAME = "golem"
    OWN_TIMEOUT = False

    @override
    def file_command(self, path: Path, timeout: int | None) -> list[str]:
        return [str(self.binary), str(path)]

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        return run_on_file([self], system, timeout)
