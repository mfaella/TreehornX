"""CHC solvers run as external processes, the system is piped on their standard input."""

import contextlib
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import IO

from treehornx.chc.smt.sexpr import CHCSystem


class Status(Enum):
    """sat = the system has a model (safe), unsat = it has none (an error is reachable)."""

    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


class SolverError(Exception):
    """The solver ended without giving a status."""


# extra seconds given to a process past its own timeout before it is killed
KILL_GRACE = 5


class CHCSolver(ABC):
    @abstractmethod
    def solve(self, system: CHCSystem, timeout: int | None = None) -> Status:
        """Whether `system` is satisfiable, UNKNOWN when the solver gives up or runs out of `timeout` seconds."""


def resolve_binary(name: str, solvers_dir: Path | None) -> Path:
    """The executable `name` in `solvers_dir`, or on PATH when the directory does not have it."""
    if solvers_dir is not None and (found := shutil.which(name, path=str(solvers_dir))) is not None:
        return Path(found)
    if (found := shutil.which(name)) is not None:
        return Path(found)
    where = f"in {solvers_dir} nor on PATH" if solvers_dir is not None else "on PATH"
    raise SolverError(f"{name} not found {where}")


def _drain(stream: IO[str], chunks: list[str]) -> threading.Thread:
    thread = threading.Thread(target=lambda: chunks.append(stream.read()), daemon=True)
    thread.start()
    return thread


def run_piped(cmd: list[str], system: CHCSystem, timeout: int | None) -> Status:
    """Runs `cmd`, writes the system on its standard input and reads the status it prints.

    The outputs are read while the system is written, so a solver printing a lot (e.g. one error per clause)
    cannot block on a full pipe while the system is still being written."""
    with subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as proc:
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        out: list[str] = []
        err: list[str] = []
        readers = [_drain(proc.stdout, out), _drain(proc.stderr, err)]
        try:
            system.write(proc.stdin)
            proc.stdin.close()
        except BrokenPipeError:  # the solver exited early, its output says why
            # closing flushes what is left in the buffer, it fails again but leaves the pipe closed
            with contextlib.suppress(BrokenPipeError):
                proc.stdin.close()
        try:
            proc.wait(timeout=None if timeout is None else timeout + KILL_GRACE)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return Status.UNKNOWN
        finally:
            for reader in readers:
                reader.join()
    stdout, stderr = "".join(out), "".join(err)
    for line in map(str.strip, stdout.splitlines()):
        if line in ("sat", "unsat", "unknown"):
            return Status(line)
        if line == "timeout":  # printed by eldarica
            return Status.UNKNOWN
    output = (stdout + stderr).strip()
    raise SolverError(f"{Path(cmd[0]).name} exited with code {proc.returncode} without a status: {output}")
