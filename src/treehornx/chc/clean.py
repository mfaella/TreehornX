"""Clean phase of a clause: the variables made equal by the body are merged into one fresh variable.

The non-predicate symbols of a clause are universally quantified, so for a top-level conjunct x = y of the body
  ∀x,y,X. (x = y ∧ B) → H  ≡  ∀z,X. B[z/x, z/y] → H[z/x, z/y]
Only positive top-level equalities between two variables are merged; every occurrence of a merged variable is
substituted, then the constraints of the body and the arguments of every application are simplified.

With `merge_leaf_constants`, in a clause whose body has no application (a fact, such as the clause of a leaf),
the variables equal to the same constant by a top-level conjunct x = c are merged too: the fact then states the
equalities between its arguments, which the solver can generalise (for instance the heights of the precondition and
of the postcondition automata, both 0 on a nil leaf).

Clauses are built uncleaned: the phase runs lazily on each clause when the system is printed (`CHCSystem.clean`).
"""

from dataclasses import dataclass, field
from functools import partial
from typing import Generic, TypeVar

from treehornx.chc.smt.preprocess import conjuncts, fresh_var, simplify_clause, substitute
from treehornx.chc.smt.sexpr import FALSE, Application, Clause, Constant, Operator, OpExpr, SExpr, Transform, Var


T = TypeVar("T")


@dataclass
class UnionFind(Generic[T]):
    _parent: dict[T, T] = field(default_factory=dict[T, T])
    _rank: dict[T, int] = field(default_factory=dict[T, int])

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


def _merged_equality(constraint: SExpr) -> tuple[Var, Var] | None:
    """The two variables of `constraint` when it is x = y."""
    match constraint:
        case OpExpr(Operator.EQ, (Var() as left, Var() as right)):
            return left, right
        case _:
            return None


def _constant_equality(constraint: SExpr) -> tuple[Var, Constant] | None:
    """The variable and the constant of `constraint` when it is x = c or c = x."""
    match constraint:
        case OpExpr(Operator.EQ, (Var() as variable, Constant() as constant)) | OpExpr(
            Operator.EQ, (Constant() as constant, Var() as variable)
        ):
            return variable, constant
        case _:
            return None


def clean_clause(clause: Clause, merge_leaf_constants: bool = False) -> Clause | None:
    """`clause` with every class of equal variables replaced by a fresh variable. With `merge_leaf_constants`, in a
    clause without applications in the body the variables equal to the same constant are in the same class.

    Returns None when the body simplifies to false: the clause is valid and says nothing."""
    flat = [c for b in clause.body for c in ((b,) if isinstance(b, Application) else conjuncts(b))]
    classes = UnionFind[Var]()
    for c in flat:
        if not isinstance(c, Application) and (pair := _merged_equality(c)) is not None:
            classes.union(*pair)
    if merge_leaf_constants and not any(isinstance(c, Application) for c in flat):
        by_constant: dict[Constant, Var] = {}
        for c in flat:
            if not isinstance(c, Application) and (pair := _constant_equality(c)) is not None:
                variable, constant = pair
                if constant in by_constant:
                    classes.union(by_constant[constant], variable)
                else:
                    by_constant[constant] = variable
    subst: dict[Var, SExpr] = {}
    for group in classes.groups():
        if len(group) < 2:
            continue
        fresh = fresh_var(group[0].type)
        subst |= {variable: fresh for variable in group}
    cleaned = simplify_clause(substitute(Clause(clause.head, *flat), subst))
    if FALSE in cleaned.body:
        return None
    return cleaned


def clean_transform(merge_leaf_constants: bool = False) -> Transform:
    """The clean phase as a printing transform."""
    return partial(clean_clause, merge_leaf_constants=merge_leaf_constants) if merge_leaf_constants else clean_clause
