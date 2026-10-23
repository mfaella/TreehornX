from pathlib import Path

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import ProcessSolver, Status, run_on_file


class GolemSolver(ProcessSolver):
    """Golem, on the system written to a file: it does not read its standard input nor take a timeout, so it is
    killed when the timeout expires. `engine` is passed as `-e <engine>`, golem's default engine otherwise."""

    NAME = "golem"
    OWN_TIMEOUT = False

    def __init__(self, solvers_dir: Path | None = None, engine: str | None = None) -> None:
        super().__init__(solvers_dir)
        self.engine = engine

    @property
    @override
    def label(self) -> str:
        return self.NAME if self.engine is None else f"{self.NAME}-{self.engine}"

    @override
    def file_command(self, path: Path, timeout: int | None) -> list[str]:
        engine_args = [] if self.engine is None else ["-e", self.engine]
        return [str(self.binary), *engine_args, str(path)]

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        return run_on_file([self], system, timeout).status
