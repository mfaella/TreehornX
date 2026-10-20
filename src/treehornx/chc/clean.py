"""Clean phase of a clause: the variables made equal by the body are merged into one fresh variable.

The non-predicate symbols of a clause are universally quantified, so for a top-level conjunct x = y of the body
  ∀x,y,X. (x = y ∧ B) → H  ≡  ∀z,X. B[z/x, z/y] → H[z/x, z/y]
Only positive top-level equalities between two variables are merged; every occurrence of a merged variable is
substituted, then body and head are simplified separately (simplifying `Implies(b, FALSE)` would give `Not(b)`).
"""

from dataclasses import dataclass, field
from typing import Iterable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
from pysmt.fnode import FNode

from treehornx.feature_flags import ENABLE_CLEAN_CLAUSE


@dataclass
class UnionFind[T]:
    _parent: dict[T, T] = field(default_factory=dict)
    _rank: dict[T, int] = field(default_factory=dict)

    def add(self, item: T) -> None:
        if item not in self._parent:
            self._parent[item] = item
            self._rank[item] = 0

    def find(self, item: T) -> T:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: T, right: T) -> None:
        left, right = self.find(left), self.find(right)
        if left == right:
            return
        if self._rank[left] < self._rank[right]:
            left, right = right, left
        self._parent[right] = left
        if self._rank[left] == self._rank[right]:
            self._rank[left] += 1

    def groups(self) -> list[list[T]]:
        """The classes, in the order their first item was added."""
        by_root: dict[T, list[T]] = {}
        for item in self._parent:
            by_root.setdefault(self.find(item), []).append(item)
        return list(by_root.values())


def conjuncts(formula: FNode) -> Iterable[FNode]:
    if formula.is_and():
        for arg in formula.args():
            yield from conjuncts(arg)
    else:
        yield formula


def _is_variable(node: FNode) -> bool:
    return node.is_symbol() and not node.symbol_type().is_function_type()


def clean_clause(body: Iterable[FNode], head: FNode) -> FNode | None:
    """The clause body → head with every class of equal variables replaced by a fresh variable.

    Returns None when the body simplifies to false: the clause is valid and says nothing."""
    if not ENABLE_CLEAN_CLAUSE:
        return chc.Clause(smt.And(*body), head)
    flat = [c for formula in body for c in conjuncts(formula)]
    classes = UnionFind[FNode]()
    for c in flat:
        if (c.is_equals() or c.is_iff()) and all(_is_variable(arg) for arg in c.args()):
            classes.union(c.arg(0), c.arg(1))
    subst: dict[FNode, FNode] = {}
    for group in classes.groups():
        if len(group) < 2:
            continue
        fresh = smt.FreshSymbol(group[0].symbol_type(), "e%d")
        subst |= {variable: fresh for variable in group}
    new_body = smt.substitute(smt.And(*flat), subst).simplify()
    new_head = smt.substitute(head, subst).simplify()
    if new_body.is_false():
        return None
    if new_body.is_true():
        return new_head
    return chc.Clause(new_body, new_head)
