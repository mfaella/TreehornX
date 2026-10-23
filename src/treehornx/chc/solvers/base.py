"""CHC solvers run as external processes, the system is piped on their standard input or written to a file."""

import contextlib
import os
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import IO, ClassVar, Sequence

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


class ProcessSolver(CHCSolver):
    """A solver binary, run on the system piped on its standard input or written to a file."""

    NAME: ClassVar[str]
    OWN_TIMEOUT: ClassVar[bool] = True
    """Whether the solver stops by itself after the timeout given on its command line, otherwise it is killed then."""

    def __init__(self, solvers_dir: Path | None = None) -> None:
        self.binary = resolve_binary(self.NAME, solvers_dir)

    @property
    def label(self) -> str:
        """The name of the solver in reports, telling apart instances run with different options."""
        return self.NAME

    @abstractmethod
    def file_command(self, path: Path, timeout: int | None) -> list[str]:
        """The command solving the system written in `path`."""

    def kill_timeout(self, timeout: int | None) -> int | None:
        """Seconds after which the process is killed."""
        if timeout is None:
            return None
        return timeout + KILL_GRACE if self.OWN_TIMEOUT else timeout


@dataclass(frozen=True)
class Outcome:
    """The status of a race, with the solver deciding it and the exact command it ran (None when none decides)."""

    status: Status
    solver: ProcessSolver | None = None
    command: tuple[str, ...] | None = None


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
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
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
            _kill(proc)
            proc.wait()
            return Status.UNKNOWN
        finally:
            for reader in readers:
                reader.join()
    return parse_status(cmd, proc.returncode, "".join(out), "".join(err))


def parse_status(cmd: list[str], returncode: int, stdout: str, stderr: str) -> Status:
    """The status printed by the solver run with `cmd`."""
    for line in map(str.strip, stdout.splitlines()):
        if line in ("sat", "unsat", "unknown"):
            return Status(line)
        if line == "timeout":  # printed by eldarica
            return Status.UNKNOWN
    output = (stdout + stderr).strip()
    raise SolverError(f"{Path(cmd[0]).name} exited with code {returncode} without a status: {output}")


def run_on_file(solvers: Sequence[ProcessSolver], system: CHCSystem, timeout: int | None) -> Outcome:
    """Writes the system to a temporary file and runs every solver on it at the same time.

    The first sat/unsat wins and the other processes are killed. UNKNOWN when no solver decides, SolverError when
    every solver ends without a status."""
    with tempfile.TemporaryDirectory(prefix="treehornx-") as directory:
        path = Path(directory) / "system.smt2"
        with path.open("w") as f:
            system.write(f)
        return race_on_file(solvers, path, timeout)


def race_on_file(solvers: Sequence[ProcessSolver], path: Path, timeout: int | None) -> Outcome:
    """Runs every solver on the system written in `path` at the same time, as `run_on_file`."""
    results: queue.Queue[tuple[ProcessSolver, list[str], Status | SolverError]] = queue.Queue()
    procs: list[subprocess.Popen[str]] = []
    waiters: list[threading.Thread] = []
    try:
        for solver in solvers:
            cmd = solver.file_command(path, timeout)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,  # its own process group, killed with the processes it starts
            )
            procs.append(proc)
            waiter = threading.Thread(
                target=_wait, args=(solver, cmd, proc, solver.kill_timeout(timeout), results), daemon=True
            )
            waiter.start()
            waiters.append(waiter)
        errors: list[SolverError] = []
        for _ in solvers:
            solver, cmd, result = results.get()
            if isinstance(result, SolverError):
                errors.append(result)
            elif result is not Status.UNKNOWN:
                return Outcome(result, solver, tuple(cmd))
        if len(errors) == len(solvers):
            raise SolverError("; ".join(map(str, errors)))
        return Outcome(Status.UNKNOWN)
    finally:
        for proc in procs:
            _kill(proc)
        for waiter in waiters:
            waiter.join()


def _wait(
    solver: ProcessSolver,
    cmd: list[str],
    proc: subprocess.Popen[str],
    kill_timeout: int | None,
    results: queue.Queue[tuple[ProcessSolver, list[str], Status | SolverError]],
) -> None:
    try:
        stdout, stderr = proc.communicate(timeout=kill_timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        proc.communicate()
        results.put((solver, cmd, Status.UNKNOWN))
        return
    try:
        results.put((solver, cmd, parse_status(cmd, proc.returncode, stdout, stderr)))
    except SolverError as e:
        results.put((solver, cmd, e))


def _kill(proc: subprocess.Popen[str]) -> None:
    """Kills the process group of `proc`: a wrapper script would otherwise leave the solver running."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
