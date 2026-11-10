"""Removal of the Lab pairs whose data constraints are unsatisfiable, checked with an SMT solver (yices2).

The constraints of a pair (parent, child, j) are the `label_constraints` of the parent and of the child and the
`consistency_constraint` linking them. Every bottom-up clause that uses the pair conjoins (at least) these
constraints, so a pair whose constraints are unsatisfiable is in no tree with satisfiable data: removing it keeps
the meaning of every system built on the labels. The labels are kept: the finals of the tainting drop the ones
left without support.

All the pairs are checked by one solver process, in incremental mode (one push/pop scope per pair).
"""

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from treehornx.chc.Lab.clauses import consistency_constraint, label_constraints
from treehornx.chc.Lab.system import LabCHC
from treehornx.chc.smt import sexpr as sx
from treehornx.chc.solvers.base import SolverError, Status, resolve_binary
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab import Lab


YICES = "yices-smt2"

NONLINEAR_OPS = frozenset({sx.Operator.MUL, sx.Operator.DIV, sx.Operator.MOD})


def pair_constraints(lab: LabCHC, pair: Pair[Lab]) -> list[sx.SExpr]:
    """The data constraints of the parent, of the child and of the link between them."""
    return [
        *label_constraints(lab.sym, pair.parent, "p_"),
        *label_constraints(lab.sym, pair.child, "c_"),
        *consistency_constraint(lab.sym, pair.parent, pair.child, pair.j, "p_", "c_"),
    ]


def _is_nonlinear(term: sx.SExpr) -> bool:
    if not isinstance(term, sx.OpExpr):
        return False
    if term.op in NONLINEAR_OPS and sum(not isinstance(arg, sx.Constant) for arg in term.args) > 1:
        return True
    return any(_is_nonlinear(arg) for arg in term.args)


def pair_script(constraints: list[list[sx.SExpr]]) -> tuple[str, bool]:
    """The incremental script checking each list of constraints in its own scope, and whether it is nonlinear."""
    nonlinear = any(_is_nonlinear(c) for cs in constraints for c in cs)
    lines = [f"(set-logic {'QF_NIA' if nonlinear else 'QF_LIA'})"]
    for cs in constraints:
        lines.append("(push 1)")
        declared = {var.name: var for c in cs for var in c.free_variables()}
        lines.extend(f"(declare-fun {var.name} () {var.type.value})" for var in declared.values())
        lines.extend(f"(assert {c.to_smt()})" for c in cs)
        lines.append("(check-sat)")
        lines.append("(pop 1)")
    lines.append("(exit)")
    return "\n".join(lines) + "\n", nonlinear


@dataclass(frozen=True)
class PruneResult:
    lab: LabCHC
    """The Lab part without the unsatisfiable pairs."""
    checked: int
    removed: int
    unknown: int


@dataclass
class PairPruner:
    """Runs yices2 on the data constraints of each pair of a Lab part."""

    binary: Path

    @classmethod
    def find(cls, solvers_dir: Path | None) -> "PairPruner":
        return cls(resolve_binary(YICES, solvers_dir))

    def statuses(self, constraints: list[list[sx.SExpr]], timeout: int | None = None) -> list[Status]:
        """The status of each list of constraints."""
        if not constraints:
            return []
        script, nonlinear = pair_script(constraints)
        command = [str(self.binary), "--incremental", *(["--mcsat"] if nonlinear else [])]
        try:
            done = subprocess.run(command, input=script, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as e:
            raise SolverError(f"{YICES} did not answer in {timeout} s") from e
        answers = [line.strip() for line in done.stdout.splitlines() if line.strip()]
        statuses = [Status(answer) for answer in answers if answer in ("sat", "unsat", "unknown")]
        if len(statuses) != len(constraints):
            raise SolverError(
                f"{YICES} gave {len(statuses)} answers for {len(constraints)} pairs: "
                f"{done.stderr.strip() or done.stdout.strip()[:500]}"
            )
        return statuses

    def prune(self, lab: LabCHC, timeout: int | None = None) -> PruneResult:
        """`lab` without the pairs whose constraints are unsatisfiable (unknown pairs are kept)."""
        pairs = list(lab.tree.pairs)
        statuses = self.statuses([pair_constraints(lab, pair) for pair in pairs], timeout)
        kept = frozenset(pair for pair, status in zip(pairs, statuses) if status is not Status.UNSAT)
        tree = replace(lab.tree, pairs=kept)
        unknown = sum(status is Status.UNKNOWN for status in statuses)
        return PruneResult(replace(lab, tree=tree), len(pairs), len(pairs) - len(kept), unknown)
