import math
import time

from typing_extensions import override

from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers.base import CHCSolver, Status


class QuerySplitterCHCSolver(CHCSolver):
    """Solves each query of the system alone, on its reachability cone, with the solver `solver`.

    The system is sat when every cone is sat (a system without queries is sat) and unsat as soon as one cone is
    unsat; the cones left are not solved then. Otherwise it is UNKNOWN. `timeout` is the budget of all the cones
    together: each cone gets the seconds left."""

    def __init__(self, solver: CHCSolver) -> None:
        self.solver = solver

    @override
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        deadline = None if timeout is None else time.monotonic() + timeout
        result = Status.SAT
        for query in system.queries():
            left = None
            if deadline is not None:
                left = math.ceil(deadline - time.monotonic())
                if left <= 0:
                    return Status.UNKNOWN
            status = self.solver.solve(system.get_reachability_cone(query), left)
            if status is Status.UNSAT:
                return Status.UNSAT
            if status is Status.UNKNOWN:
                result = Status.UNKNOWN
        return result
