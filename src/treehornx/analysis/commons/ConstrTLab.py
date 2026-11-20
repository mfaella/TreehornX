"""ConstrTLab: a TLab and its constraints, the common interface of the preprocessing phases.

A `ConstrTLab` gives everything the CHC systems read from a node:

* `symbols(role)`: all the symbols of the label (the data of every frame, the states of the automata);
* `args(role)`: the symbols that are arguments of its predicate: the data of the first frame, of the last frame and
  of every frame reached or left by a non-internal step (`kept_frames`), and the states of the automata;
* `constraints(role)`: the internal constraints of the label (quantified symbols included);
* `ConstrTLab.consistency_constraints(parent, child, j)`: the constraints of the link between a parent and its j-th
  child, on the symbols of the parent with the role `Parent()` and those of the child with the role `Slot(j)`;
* `rename(expr, role)`: an expression written on the symbols of the TLab, on the arguments of the label;
* `apply(role, suffix)`: the predicate `THX<suffix>` on `args(role)` and the error flag `e<n>`;
* `error_constraints(n, role)` and `ConstrTLab.edge_error_constraints(parent, child, j)`: the constraints of the
  error flag (`ConstraintsBuilder.error_constraints`, `edge_error_constraints`).

The base class holds the constraints of the TLab, made by its `ConstraintsBuilder`: the Lab encoding and, when the
builder has them, the precondition (its states, ψ, ψ_F) and the negated postcondition A¬post (its states and the
constraints S1-S4); the taints are in the TLab.
Each phase builds, from a label and the result of its analysis, a new label that changes the constraints:
`EqConstrTLab` replaces each class of equal symbols by a new symbol, `ConstConstrTLab` each symbol equal to a
constant by the constant (both with `SExpr.substitute`).
"""

from __future__ import annotations

from functools import cached_property

from typing_extensions import override

from treehornx import smt as sx
from treehornx.analysis.constraints import symbols as sy
from treehornx.analysis.constraints.symbols import Role
from treehornx.analysis.constraints.ConstraintsBuilder import ConstraintsBuilder
from treehornx.enum_models.labels import Internal, TLab
from treehornx.smt.sexpr import Application, Predicate


PREDICATE_PREFIX = "THX"


class ConstrTLab:
    """A TLab with its constraints: those of its Lab label and, when the builder has them, those of the
    precondition (`builder.pre`) and of A¬post (`builder.post`)."""

    def __init__(self, tlab: TLab, builder: ConstraintsBuilder) -> None:
        self.tlab = tlab
        self.builder = builder

    # identity ----------------------------------------------------------------

    def key(self) -> tuple[object, ...]:
        """What identifies the label (its constraints follow from it)."""
        return (self.tlab,)

    @cached_property
    def _hash(self) -> int:
        return hash((type(self), self.key()))

    @override
    def __hash__(self) -> int:
        return self._hash

    @override
    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        if not isinstance(other, ConstrTLab) or type(other) is not type(self):
            return False
        return self._hash == other._hash and self.key() == other.key()

    @override
    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self.tlab.lab)} frames, {len(self.args())} args)"

    # interface ---------------------------------------------------------------

    def _kept_frames(self) -> list[int]:
        """The positions of the frames whose data are arguments of the predicate: the first frame, the last frame
        and every intermediate frame whose `prev` or `next` is not `Internal` (reached or left through another node).
        An intermediate frame of an internal chain is dropped: its data only occur as quantified symbols."""
        lab = self.tlab.lab
        a = len(lab)
        return [i for i in range(1, a + 1) if i in (1, a) or lab[i].prev != Internal() or lab[i].next != Internal()]

    @cached_property
    def _states(self) -> tuple[sy.Symbol, ...]:
        """The states of the automata of the builder: the precondition, then A¬post."""
        pre = self.builder.pre_symbols(self.tlab)
        post = self.builder.post_symbols(self.tlab)
        return (*pre, *post)

    @cached_property
    def _symbols(self) -> tuple[sy.Symbol, ...]:
        return (*self.builder.label_symbols(self.tlab.lab), *self._states)

    @cached_property
    def _args(self) -> tuple[sy.Symbol, ...]:
        frames = (s for i in self._kept_frames() for s in self.builder.frame_symbols(i))
        return (*frames, *self._states)

    def symbols(self, role: Role | None = None) -> list[sy.Symbol]:
        """All the symbols of the label, in order: the data of every frame (those that are not arguments of the
        predicate included) and the states of the automata, named for `role` (`sy.prefix_of`)."""
        return [s.with_role(role) for s in self._symbols]

    def args(self, role: Role | None = None) -> list[sy.Symbol]:
        """The arguments of the predicate of the label, in order: the data of the kept frames (`kept_frames`) and
        the states of the automata, named for `role` (`sy.prefix_of`)."""
        return [s.with_role(role) for s in self._args]

    def arg_types(self) -> list[sx.Type]:
        return [s.type for s in self._args]

    def constraints(self, role: Role | None = None) -> list[sx.SExpr]:
        """The internal constraints of the label (on its arguments and on quantified symbols)."""
        constraints = self.builder.label_constraints(self.tlab.lab, role)
        constraints += self.builder.pre_constraints(self.tlab, role)
        constraints += self.builder.post_constraints(self.tlab, role)
        return constraints

    def rename(self, expr: sx.SExpr, role: Role | None = None) -> sx.SExpr:
        """`expr`, written on the symbols of the TLab, on the arguments of the label."""
        return expr

    @staticmethod
    def consistency_constraints(parent: ConstrTLab, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        """The constraints between `parent` (role `Parent()`) and its j-th child `child` (role `Slot(j)`)."""
        return parent.consistency(child, j)

    def consistency(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        constraints = self.builder.consistency_constraint(self.tlab.lab, child.tlab.lab, j)
        constraints += self.builder.pre_consistency(self.tlab, child.tlab, j)
        constraints += self.builder.post_consistency(self.tlab, child.tlab, j)
        return constraints

    # predicates and error flag -----------------------------------------------

    def apply(self, role: Role | None = None, suffix: str = "") -> Application:
        """The predicate `THX<suffix>` applied to `args(role)` and the error flag `e<n>`. `suffix` is `<id>_<n>`:
        `n`, the text after its last `_`, is the number of children collected and selects the flag."""
        n = int(suffix.rsplit("_", 1)[-1])
        predicate = Predicate.make(name=f"{PREDICATE_PREFIX}{suffix}", types=[*self.arg_types(), sx.Type.Bool])
        return Application.make(predicate=predicate, args=[*self.args(role), sy.Symbol.error(n, role)])

    def error_constraints(self, n: int, role: Role | None = None) -> list[sx.SExpr]:
        """`e<n>` equals the error of the label (`ConstraintsBuilder.error_constraints`)."""
        return self.builder.error_constraints(self.tlab, n, role)

    @staticmethod
    def edge_error_constraints(parent: ConstrTLab, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        """The flag of `parent` after its j-th child `child` is collected (`ConstraintsBuilder.edge_error_constraints`),
        parent with the role `Parent()`, child with `Slot(j)`."""
        return parent.edge_error(child, j)

    def edge_error(self, child: ConstrTLab, j: int) -> list[sx.SExpr]:
        return self.builder.edge_error_constraints(self.tlab, child.tlab, j)
