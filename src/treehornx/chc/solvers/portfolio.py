from pathlib import Path
from typing import Sequence

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import CHCSolver, Outcome, ProcessSolver, Status, run_on_file
from treehornx.chc.solvers.eldarica import EldaricaSolver
from treehornx.chc.solvers.golem import GolemSolver
from treehornx.chc.solvers.z3 import Z3Solver


class PortfolioSolver(CHCSolver):
    """Golem (with its engines for non-linear systems, spacer and pa), Spacer and Eldarica run at the same time on
    the system written to a temporary file: the first one deciding gives the status, the others are killed."""

    def __init__(self, solvers_dir: Path | None = None, solvers: Sequence[ProcessSolver] | None = None) -> None:
        self.solvers = (
            list(solvers)
            if solvers is not None
            else [
                GolemSolver(solvers_dir, engine="spacer"),
                GolemSolver(solvers_dir, engine="pa"),
                Z3Solver(solvers_dir),
                EldaricaSolver(solvers_dir),
            ]
        )

    def race(self, system: CHCSystem, timeout: int | None = None) -> Outcome:
        """The status, with the solver deciding it and the command it ran."""
        return run_on_file(self.solvers, system, timeout)

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        return self.race(system, timeout).status
