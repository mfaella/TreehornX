from treehornx import ir
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.system import build_lab, to_system
from treehornx.chc.pre.PreRunner import PreRunner
from treehornx.chc.pre.runner import BotUpAutomataRunner
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.feature_flags import FeatureFlags


def make_system(
    function: ir.Function,
    k: int,
    m: int,
    n: int,
    ctx: SDTAContext,
    flags: FeatureFlags,
    exit_codes: frozenset[ExitCodeKind] = frozenset({ExitCodeKind.ERR}),
) -> CHCSystem:
    """Lab clauses plus the precondition layer: unsat iff an input accepted by `ctx` leads to an exit status in
    `exit_codes`."""
    lab = build_lab(function, k, m, n, flags)
    runner = PreRunner(function, lab.pairs, ctx, k, m, sym=lab.sym, n=n, exit_codes=exit_codes, flags=flags)
    return to_system(
        [*lab.predicate_symbols(), *runner.predicates()],
        [*lab.clauses, *runner.clauses(), *runner.queries()],
        flags.clean_clause,
    )


__all__ = ["BotUpAutomataRunner", "PreRunner", "make_system"]
