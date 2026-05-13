from dataclasses import dataclass
from functools import cached_property
from typing import Any, Callable, Iterable

from treehornx.chc.core import ExitCodeKind
from treehornx.enum_labels._internal.EnumLabelGenerator import EnumLabelGenerator
from treehornx.enum_labels._internal.StatesDB import StatesDB
from treehornx.enum_labels.core.Dir import Dir, Internal
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Here
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


class KnittedTrees:
    def __init__(
        self,
        k: int,
        m: int,
        n: int,
        root_name: str,
        labels: Iterable[Label],
        endless_loop_pivots: Iterable[Label],
        steps: Iterable[Step],
        pairs: Iterable[tuple[Label, Label, int | str]],
    ):
        self.k = k
        self.m = m
        self.n = n
        self._root_name = root_name
        self._labels = set(labels)
        self._endless_loop_pivots = set(endless_loop_pivots)
        self._steps = set(steps)
        self._ids = dict((lab, id) for id, lab in enumerate(self._labels))
        self._pairs = set(pairs)

    @cached_property
    def _safe_for(self) -> dict[ExitCodeKind, bool]:
        safe_for = {ExitCodeKind.ERR: True, ExitCodeKind.LABEL_OVERFLOW: True, ExitCodeKind.OOM: True}
        for lab in self._labels:
            if ERR() in lab.frame.events:
                safe_for[ExitCodeKind.ERR] = False
            if OOM() in lab.frame.events:
                safe_for[ExitCodeKind.OOM] = False
            if LOF() in lab.frame.events:
                safe_for[ExitCodeKind.LABEL_OVERFLOW] = False
        return safe_for

    def is_trivially_safe_for(self, exit_code: ExitCodeKind) -> bool:
        if exit_code == ExitCodeKind.CLEAN:
            raise ValueError(f"Unsupported exit code: {exit_code}")
        return self._safe_for[exit_code]

    def is_backbone_label(self, lab: Label) -> bool:
        # A label is a backbone label if it has no ancestors (i.e., no incoming edges in the dependency graph)
        return lab.origin is None

    def is_root_label(self, lab: Label) -> bool:
        if len(lab) <= 1:
            return False

        return lab[1].prev == (Internal(), 1)

    def is_start_label(self, lab: Label) -> bool:
        if not self.is_root_label(lab):
            return False

        if lab[1].pc != 0:
            return False

        if lab[1].active:
            if lab[1].events != frozenset({Here(self._root_name)}):
                return False
            for p, isnil in lab[1].isnil.items():
                if p == self._root_name and isnil:
                    return False
                if p != self._root_name and not isnil:
                    return False

            for j in range(self.k, self.k + self.m):
                if lab[1].active_child[j]:
                    return False
        else:
            if lab[1].events != frozenset({}):
                return False
            if any(not isnil for isnil in lab[1].isnil.values()):
                return False

            if any(active_child for active_child in lab[1].active_child.values()):
                return False

        return True

    def backbone_labels(self) -> Iterable[Label]:
        return filter(self.is_backbone_label, self._labels)

    def root_labels(self) -> Iterable[Label]:
        return filter(self.is_root_label, self._labels)

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

    def pairs_by_parent_and_child_key(
        self, parent: Label, child_key: int | str
    ) -> Iterable[tuple[Label, Label, int | str]]:
        return filter(lambda p: p[0] == parent and p[2] == child_key, self.pairs())

    @cached_property
    def child_keys(self) -> set[int | str]:
        return set(p[2] for p in self._pairs)

    def pairs(self) -> Iterable[tuple[Label, Label, int | str]]:
        return iter(self._pairs)

    @cached_property
    def root_name(self) -> str:
        return self._root_name


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


def generate_labels(
    func: Function,
    root: Var,
    m: int,
    n: int,
    c: int | None = None,
    backbone_label_filter: Callable[[Label, bool], bool] | None = None,
    backbone_pair_filter: Callable[[tuple[Label, Label, int | str], bool], bool] | None = None,
) -> KnittedTrees:
    if root not in func.vars:
        raise RootRefVariableNotFoundError(f"Root reference variable '{root.name}' not found in the function.")
    def default_filter(arg: Any, is_root: bool) -> bool:
        return True

    generator = EnumLabelGenerator(
        func,
        root,
        m,
        n,
        c,
        backbone_label_filter=backbone_label_filter or default_filter,
        backbone_pair_filter=backbone_pair_filter or default_filter,
    )
    generator.generate()
    result = KnittedTrees(
        generator.k,
        generator.m,
        generator.n,
        root.name,
        labels=generator.db.find_all_labels(),
        endless_loop_pivots=filter(generator.db.is_endless_loop_pivot, generator.db.find_all_labels()),
        steps=_get_steps(generator.db),
        pairs=map(lambda p: (p.parent, p.child, p.child_key), generator.db.find_all_pairs()),
    )
    return result
