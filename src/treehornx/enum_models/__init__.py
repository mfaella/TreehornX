from dataclasses import dataclass
from functools import cached_property
from typing import Iterable

from treehornx import ir
from treehornx.chc.core import ExitCodeKind
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.core.SymbolicEngine import Transition
from treehornx.enum_models.Lab import (
    ERR,
    OOM,
    Frame,
    Lab,
    LabEngine,
    backbone_labels,
    initial_pairs,
    start_labels,
)


@dataclass(frozen=True)
class KnittedTrees:
    """Labels and pairs of the (m, n)-knitted-trees of a program, as computed by LabEngine."""

    engine: LabEngine
    _start_labels: frozenset[Lab]
    _backbone_labels: frozenset[Lab]

    @property
    def k(self) -> int:
        return self.engine.k

    @property
    def m(self) -> int:
        return self.engine.m

    @property
    def n(self) -> int:
        return self.engine.n

    @cached_property
    def _labels(self) -> frozenset[Lab]:
        return frozenset(self.engine.labels | self._start_labels | self._backbone_labels)

    @cached_property
    def _ids(self) -> dict[Lab, int]:
        return {lab: id for id, lab in enumerate(self._labels)}

    @cached_property
    def _safe_for(self) -> dict[ExitCodeKind, bool]:
        safe_for = {ExitCodeKind.ERR: True, ExitCodeKind.LABEL_OVERFLOW: True, ExitCodeKind.OOM: True}
        for lab in self.end_labels():
            if isinstance(lab.frame.event, ERR):
                safe_for[ExitCodeKind.ERR] = False
            if isinstance(lab.frame.event, OOM):
                safe_for[ExitCodeKind.OOM] = False
            if len(lab) == self.n + 1:
                safe_for[ExitCodeKind.LABEL_OVERFLOW] = False
        return safe_for

    def is_trivially_safe_for(self, exit_code: ExitCodeKind) -> bool:
        if exit_code == ExitCodeKind.CLEAN:
            raise ValueError(f"Unsupported exit code: {exit_code}")
        return self._safe_for[exit_code]

    def is_backbone_label(self, lab: Lab) -> bool:
        return lab in self._backbone_labels

    def is_start_label(self, lab: Lab) -> bool:
        return lab in self._start_labels

    def is_end_of_lace(self, lab: Lab) -> bool:
        return self.engine.is_end_of_lace(lab)

    def backbone_labels(self) -> Iterable[Lab]:
        return iter(self._backbone_labels)

    def start_labels(self) -> Iterable[Lab]:
        return iter(self._start_labels)

    def end_labels(self) -> Iterable[Lab]:
        return filter(self.is_end_of_lace, self._labels)

    def labels(self) -> Iterable[Lab]:
        return iter(self._labels)

    def pairs(self) -> Iterable[Pair[Frame]]:
        return iter(self.engine.pairs)

    def steps(self) -> Iterable[Transition[Frame]]:
        for transitions in self.engine.transitions.values():
            yield from transitions

    def id(self, lab: Lab) -> int:
        return self._ids[lab]

    def pairs_by_parent_and_child_key(self, parent: Lab, j: int) -> Iterable[Pair[Frame]]:
        return (p for p in self.engine.pair_parent_index[parent] if p.j == j)

    def finals(self) -> tuple[set[Lab], set[Pair[Frame]]]:
        """Labels and pairs connected to the end of some lace."""
        return self.engine.finals()


def generate_labels(function: ir.Function, m: int, n: int) -> KnittedTrees:
    starts = frozenset(start_labels(function, m))
    backbones = frozenset(backbone_labels(function, m))
    engine = LabEngine(
        function.node.k,
        m,
        n,
        initial_pairs=set(initial_pairs(function, m, starts, backbones)),
        start_labels=set(starts),
        function=function,
    )
    engine.fix()
    return KnittedTrees(engine, starts, backbones)
