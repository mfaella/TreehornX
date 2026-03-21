from dataclasses import dataclass

from .Pair import Pair


@dataclass(frozen=True)
class ExternalStepResult:
    pair: Pair


@dataclass(frozen=True)
class InternalStepResult:
    pairs: tuple[Pair, ...]


@dataclass(frozen=True)
class StepFailed:
    pass


KnitResult = ExternalStepResult | InternalStepResult | StepFailed
