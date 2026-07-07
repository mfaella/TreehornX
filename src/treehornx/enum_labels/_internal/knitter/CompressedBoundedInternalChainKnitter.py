from collections import deque
from dataclasses import dataclass, replace
from typing import Callable, override

from treehornx.enum_labels.core.Event import LOF
from treehornx.enum_labels.core.Frame import Frame
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.function import Function

from .CompressedKnitter import CompressedKnitter
from .IKnitter import IKnitter
from .KnitResult import ExternalStepResult, InternalStepResult, KnitResult, StepFailed
from .Pair import Pair


@dataclass(init=False)
class CompressedBoundedInternalChainKnitter(IKnitter):
    def __init__(
        self,
        function: Function,
        k: int,
        m: int,
        n: int,
        c: int,  # the bound on the internal steps chain length
        *,
        parent: str | None = None,
        make_label: Callable[[Label | None, Frame], Label] = lambda o, f: Label(f, o),
        on_new_internal_step: Callable[[Pair, Pair], None] = lambda ancestor, lab: None,
        on_new_external_step: Callable[[Pair, Pair], None] = lambda previous, lab: None,
        on_step_failed: Callable[[Pair], None] = lambda p: None,
    ):
        if c <= 0:
            raise ValueError("c must be a positive integer")
        self.c = c
        self._make_label = make_label
        self._knitter: IKnitter = CompressedKnitter(function, k, m, n, parent, make_label)
        self._on_new_internal_step = on_new_internal_step
        self._on_new_external_step = on_new_external_step
        self._on_step_failed = on_step_failed

    def _knit_internal_steps_chain(self, pair: Pair) -> InternalStepResult:
        queue: deque[tuple[Pair, int]] = deque([(pair, 0)])
        final_pairs: set[Pair] = set()
        while queue:
            current_pair, length = queue.popleft()
            if length >= self.c:
                last_frame = current_pair.leader().frame
                # last_frame.prev[0] == Internal() is guaranteed by the lowest possible value of c being 1,
                # which means that the current pair is the result of an internal step from the original pair,
                # so we can be sure that the last frame of the current pair is the one added by that internal step,
                # and thus it has to have an Internal() dir
                new_last_frame = replace(last_frame, events=last_frame.events | {LOF()})
                new_leader = self._make_label(current_pair.leader().origin, new_last_frame)
                new_pair = current_pair.replace_leader(new_leader)
                self._on_new_internal_step(current_pair, new_pair)
                final_pairs.add(new_pair)
                continue

            knit_result = self._knitter.knit(current_pair)
            match knit_result:
                case ExternalStepResult(p_):
                    final_pairs.add(current_pair)
                    self._on_new_external_step(current_pair, p_)
                case StepFailed():
                    final_pairs.add(current_pair)
                    self._on_step_failed(current_pair)
                case InternalStepResult(ps):
                    for p_ in ps:
                        self._on_new_internal_step(current_pair, p_)
                        queue.append((p_, length + 1))

        return InternalStepResult(tuple(final_pairs))

    @override
    def knit(self, pair: Pair) -> KnitResult:
        knit_result = self._knitter.knit(pair)
        match knit_result:
            case InternalStepResult(_):
                return self._knit_internal_steps_chain(pair)
            case ExternalStepResult(p_):
                self._on_new_external_step(pair, p_)
                return knit_result
            case StepFailed():
                self._on_step_failed(pair)
                return knit_result
