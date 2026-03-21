from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, override

from treehornx.chc.core.Dir import Internal
from treehornx.chc.core.Frame import Frame
from treehornx.chc.core.Label import Label
from treehornx.ir.function import Function

from .CompressedKnitter import CompressedKnitter
from .IKnitter import IKnitter
from .KnitResult import ExternalStepResult, InternalStepResult, KnitResult, StepFailed
from .Pair import Pair


class _VertexColor(Enum):
    WHITE = 1
    GRAY = 2
    BLACK = 3


@dataclass(init=False)
class CompressedUnboundedInternalChainKnitter(IKnitter):
    def __init__(
        self,
        function: Function,
        k: int,
        m: int,
        n: int,
        *,
        make_label: Callable[[Label | None, Frame], Label] = lambda o, f: Label(f, o),
        on_endless_loop_detected: Callable[[Pair], None] = lambda pivot: None,
        on_new_internal_step: Callable[[Pair, Pair], None] = lambda ancestor, lab: None,
        on_new_external_step: Callable[[Pair, Pair], None] = lambda previous, lab: None,
        on_step_failed: Callable[[Pair], None] = lambda p: None,
    ):
        self._knitter: IKnitter = CompressedKnitter(function, k, m, n, make_label)
        self._on_endless_loop_detected = on_endless_loop_detected
        self._on_new_internal_step = on_new_internal_step
        self._on_new_external_step = on_new_external_step
        self._on_step_failed = on_step_failed

    def _knit_internal_steps_chain(
        self,
        pair: Pair,
        loop_pivots: set[Pair] | None = None,
        colors: defaultdict[Pair, _VertexColor] | None = None,
    ) -> InternalStepResult:
        """dfs like visit to knit the internal steps chain,
        returns True if from the current pair we can reach an end of the chain, False otherwise"""
        if colors is None:
            colors = defaultdict(lambda: _VertexColor.WHITE)
        if loop_pivots is None:
            loop_pivots = set()
        colors[pair] = _VertexColor.GRAY
        knit_result = self._knitter.knit(pair)
        match knit_result:
            case ExternalStepResult(_) | StepFailed():  # base case
                return InternalStepResult((pair,))
            case InternalStepResult(ps):
                final_pairs: list[Pair] = []
                for p_ in ps:
                    self._on_new_internal_step(pair, p_)
                    match colors[p_]:
                        case _VertexColor.WHITE:
                            final_pairs.extend(self._knit_internal_steps_chain(p_, loop_pivots, colors).pairs)
                        case _VertexColor.GRAY:
                            loop_pivots.add(p_)
                        case _VertexColor.BLACK:
                            pass
                colors[pair] = _VertexColor.BLACK
                if not final_pairs and pair in loop_pivots:  # is an endless loop pivot
                    self._on_endless_loop_detected(pair)
                    return InternalStepResult((pair,))
                else:
                    return InternalStepResult(tuple(final_pairs))

    @override
    def knit(self, pair: Pair) -> KnitResult:
        knit_result = self._knitter.knit(pair)
        match knit_result:
            case InternalStepResult(ps):
                return self._knit_internal_steps_chain(pair)
            case ExternalStepResult(p_):
                self._on_new_external_step(pair, p_)
                return knit_result
            case StepFailed():
                self._on_step_failed(pair)
                return knit_result
