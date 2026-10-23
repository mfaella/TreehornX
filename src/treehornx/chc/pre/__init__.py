from treehornx import ir
from treehornx.chc.core import ExitCodeKind
from treehornx.chc.Lab.system import build_lab, to_system
from treehornx.chc.pre.PreRunner import PreRunner, label_exit
from treehornx.chc.pre.runner import BotUpAutomataRunner
from treehornx.chc.sdta.SDTAContext import SDTAContext, true_ctx
from treehornx.chc.smt.sexpr import CHCSystem
from treehornx.feature_flags import FeatureFlags


def make_system(
    function: ir.Function,
    k: int,
    m: int,
    n: int,
    ctx: SDTAContext | None,
    flags: FeatureFlags,
    exit_codes: frozenset[ExitCodeKind] = frozenset({ExitCodeKind.ERR}),
) -> CHCSystem:
    """The automaton of `ctx` run over the backbone: unsat iff an input accepted by `ctx` leads to an exit status
    in `exit_codes`. Without `ctx` every input is accepted (plain memory safety)."""
    lab = build_lab(function, k, m, n)
    runner = PreRunner(function, lab.pairs, ctx or true_ctx(), k, m, sym=lab.sym, n=n, exit_codes=exit_codes)
    return to_system(runner.predicates(), [*runner.clauses(), *runner.queries()], flags.clean_clause)


__all__ = ["BotUpAutomataRunner", "PreRunner", "label_exit", "make_system"]
