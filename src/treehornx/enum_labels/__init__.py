from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Iterable

import networkx as nx

from treehornx.enum_labels._internal.EnumLabelGenerator import EnumLabelGenerator
from treehornx.enum_labels._internal.StatesDB import StatesDB
from treehornx.enum_labels.core.Dir import Dir, Internal
from treehornx.enum_labels.core.Event import Event
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.expressions import Var
from treehornx.ir.function import Function


class RootRefVariableNotFoundError(Exception):
    pass


@dataclass(slots=True, frozen=True)
class Step:
    in_label: Label
    out_label: Label
    dir: Dir


class LaceOverApproximation:
    def __init__(
        self,
        start_labels: Iterable[Label],
        labels: Iterable[Label],
        endless_loop_pivots: Iterable[Label],
        steps: Iterable[Step],
    ):
        self._start_labels = set(start_labels)
        self._labels = set(labels)
        self._endless_loop_pivots = set(endless_loop_pivots)
        self._steps = set(steps)
        self._ids = dict((lab, id) for id, lab in enumerate(self._labels))

    def is_backbone_label(self, lab: Label) -> bool:
        # A label is a backbone label if it has no ancestors (i.e., no incoming edges in the dependency graph)
        return lab.origin is None

    def is_start_label(self, lab: Label) -> bool:
        # A label is a start label if it has no ancestors (i.e., no incoming edges in the dependency graph)
        return lab in self._start_labels

    def backbone_labels(self) -> Iterable[Label]:
        return filter(self.is_backbone_label, self._labels)

    def start_labels(self) -> Iterable[Label]:
        return filter(self.is_start_label, self._labels)

    def labels(self) -> Iterable[Label]:
        return iter(self._labels)

    def steps(self) -> Iterable[Step]:
        return iter(self._steps)

    def id(self, lab: Label) -> int:
        return self._ids[lab]

    def is_endless_loop_pivot(self, lab: Label) -> bool:
        return lab in self._endless_loop_pivots


def _get_steps(states: StatesDB) -> Iterable[Step]:
    for pair in states.find_all_pairs():
        prev = pair.leader().frame.prev
        if prev is None:
            continue
        if prev[0] != Internal() and prev[0] == pair.dir():
            yield Step(pair.follower(), pair.leader(), pair.rev_dir())

    for lab in states.find_all_labels():
        prev = lab.frame.prev
        if prev is None:
            continue
        if prev[0] == Internal():
            for ancestors in states.get_ancestors(lab):
                yield Step(ancestors, lab, Internal())


def generate_labels(func: Function, root: Var, m: int, n: int, c: int | None = None) -> LaceOverApproximation:
    if root not in func.vars:
        raise RootRefVariableNotFoundError(f"Root reference variable '{root.name}' not found in the function.")
    generator = EnumLabelGenerator(func, root, m, n, c)
    generator.generate()
    result = LaceOverApproximation(
        start_labels=map(lambda p: p.leader(), generator.initial_root_pairs()),
        labels=generator.db.find_all_labels(),
        endless_loop_pivots=filter(generator.db.is_endless_loop_pivot, generator.db.find_all_labels()),
        steps=_get_steps(generator.db),
    )
    return result
