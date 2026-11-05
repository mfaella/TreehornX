"""QuerySplitterCHCSolver on a fake solver: each query is solved alone on its cone."""

from typing_extensions import override

from treehornx.chc.smt import sexpr as sx
from treehornx.chc.solvers import CHCSolver, QuerySplitterCHCSolver, Status


X = sx.Var("x", sx.Type.Int)
P = sx.Predicate("P", [sx.Type.Int])
R = sx.Predicate("R", [sx.Type.Int])
P_FACT = sx.Clause(sx.Application(P, X), sx.OpExpr(sx.Operator.EQ, X, 0))
R_FACT = sx.Clause(sx.Application(R, X), sx.OpExpr(sx.Operator.EQ, X, 1))
P_QUERY = sx.Clause(False, sx.Application(P, X))
R_QUERY = sx.Clause(False, sx.Application(R, X))
TIMEOUT = 60
SYSTEM = sx.CHCSystem([P, R], [P_FACT, R_FACT, P_QUERY, R_QUERY])


class FakeSolver(CHCSolver):
    """Gives the status of the query of each system it is called on, and records the systems and timeouts."""

    def __init__(self, statuses: dict[sx.Clause, Status]) -> None:
        self.statuses = statuses
        self.calls: list[tuple[list[sx.Clause], int | None]] = []

    @override
    def solve(self, system: sx.CHCSystem, timeout: int | None = None) -> Status:
        self.calls.append((system.clauses, timeout))
        (query,) = system.queries()
        return self.statuses[query]


def test_each_query_on_its_cone() -> None:
    fake = FakeSolver({P_QUERY: Status.SAT, R_QUERY: Status.SAT})
    assert QuerySplitterCHCSolver(fake).solve(SYSTEM) is Status.SAT
    assert fake.calls == [([P_FACT, P_QUERY], None), ([R_FACT, R_QUERY], None)]


def test_unsat_stops() -> None:
    fake = FakeSolver({P_QUERY: Status.UNSAT, R_QUERY: Status.SAT})
    assert QuerySplitterCHCSolver(fake).solve(SYSTEM) is Status.UNSAT
    assert len(fake.calls) == 1


def test_unknown_does_not_hide_unsat() -> None:
    fake = FakeSolver({P_QUERY: Status.UNKNOWN, R_QUERY: Status.UNSAT})
    assert QuerySplitterCHCSolver(fake).solve(SYSTEM) is Status.UNSAT
    fake = FakeSolver({P_QUERY: Status.UNKNOWN, R_QUERY: Status.SAT})
    assert QuerySplitterCHCSolver(fake).solve(SYSTEM) is Status.UNKNOWN


def test_no_query_is_sat() -> None:
    fake = FakeSolver({})
    assert QuerySplitterCHCSolver(fake).solve(sx.CHCSystem([P], [P_FACT])) is Status.SAT
    assert not fake.calls


def test_timeout_is_a_total_budget() -> None:
    fake = FakeSolver({P_QUERY: Status.SAT, R_QUERY: Status.SAT})
    QuerySplitterCHCSolver(fake).solve(SYSTEM, timeout=TIMEOUT)
    assert all(timeout is not None and 0 < timeout <= TIMEOUT for _, timeout in fake.calls)
