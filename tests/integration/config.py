"""Per-test configuration of the integration tests.

Every case is a `TestConfig`, turned into a `pytest.param` by `params` and run by `run`: it fixes the
program, the bounds, the input restrictions (nil fields, precondition), the feature flags, the solver and
the expected status, the same choices as the `treehornx verify` options.
"""

import multiprocessing
import shutil
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

import pytest
from _pytest.mark import ParameterSet

from treehornx.chc import Lab, pre
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.chc.solvers import CHCSolver, EldaricaSolver, Status, Z3Solver
from treehornx.feature_flags import FeatureFlags
from treehornx.main import DEFAULT_N, PRE, PreType, label_exit, with_nil_fields
from treehornx.parser import parse_file


C_FILES = Path(__file__).parent / "c_files"
SOLVERS_DIR = Path(__file__).parent / "solvers"

SolverName: TypeAlias = Literal["z3", "eldarica"]

SOLVERS: dict[SolverName, type[Z3Solver | EldaricaSolver]] = {
    "z3": Z3Solver,
    "eldarica": EldaricaSolver,
}


@dataclass(frozen=True)
class TestConfig:
    __test__ = False  # not a test class, pytest must not collect it

    program: str
    """Name of the C file in `c_files`, without extension."""
    expected: Status
    """sat = safe, unsat = `exit_code` is reachable."""
    m: int = 0
    n: int = DEFAULT_N
    nil_fields: tuple[str, ...] = ()
    """Pointer fields nil in every input node (`--nil-field`)."""
    pre: PreType | None = None
    flags: FeatureFlags = field(default_factory=FeatureFlags)
    solver: SolverName = "z3"
    timeout: int = 120
    exit_code: ExitCodeKind = ExitCodeKind.ERR
    id: str | None = None
    """Test id, the program name followed by the precondition by default."""
    marks: tuple[pytest.MarkDecorator, ...] = field(default=(), compare=False)

    @property
    def test_id(self) -> str:
        if self.id is not None:
            return self.id
        return self.program if self.pre is None else f"{self.program}-{self.pre}"


def solver_dir(name: SolverName) -> Path | None:
    """The directory shipping the solver binary, None to look it up on PATH."""
    return SOLVERS_DIR if shutil.which(SOLVERS[name].NAME, path=str(SOLVERS_DIR)) else None


def solver_available(name: SolverName) -> bool:
    return solver_dir(name) is not None or shutil.which(SOLVERS[name].NAME) is not None


def params(*configs: TestConfig) -> list[ParameterSet]:
    """One `pytest.param` per config, skipped when its solver is not available."""
    result: list[ParameterSet] = []
    for config in configs:
        marks = list(config.marks)
        if not solver_available(config.solver):
            marks.append(pytest.mark.skip(reason=f"{SOLVERS[config.solver].NAME} executable not found"))
        result.append(pytest.param(config, id=config.test_id, marks=marks))
    return result


def make_system(config: TestConfig) -> CHCSystem:
    function = parse_file(str(C_FILES / f"{config.program}.c"))
    if config.nil_fields:
        restricted = with_nil_fields(function, list(config.nil_fields))
        assert restricted is not None, f"{config.program} has no pointer field among {config.nil_fields}"
        function = restricted
    k = function.node.k
    if config.pre is None:
        return Lab.make_system(
            function, k, config.m, config.n, lambda label: config.exit_code in label_exit(label, config.n), config.flags
        )
    return pre.make_system(
        function, k, config.m, config.n, PRE[config.pre](), config.flags, frozenset({config.exit_code})
    )


def _solve(config: TestConfig) -> Status:
    solver: CHCSolver = SOLVERS[config.solver](solver_dir(config.solver))
    return solver.solve(make_system(config), config.timeout)


def run(config: TestConfig) -> Status:
    """Builds and solves the system in a forked process: PyPy keeps the memory a large system takes for the
    rest of the session, a process exiting returns it to the OS. Exceptions are raised again here."""
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("fork")) as executor:
        return executor.submit(_solve, config).result()
