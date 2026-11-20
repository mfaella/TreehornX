"""The symbols of a node of the CHC systems, independent of the place of the node in a clause.

The place of a node in a clause is its `Role`: `Parent()` names its symbols with the prefix `p_`, `Slot(j)` (the
j-th child) with the prefix `c<j>_`; no role (None) gives the bare names. A `Symbol` identifies one argument of a node
(or one quantified variable of its constraints) and `with_role(role)` gives the same symbol in another place of a
clause; every module builds its variables through `Symbol`, so the names have a single definition (`base_name` is
the bare name, `name` adds the prefix of the role):

* `Symbol.local(id, i, type)`: the data variable `id` at the frame i, `<prefix>v<id>_<i>`;
* `Symbol.field(id, i, type)`: the data field `id` at the frame i, `<prefix>f<id>_<i>`;
* `Symbol.pre_node(state, type)`: a component of the state of the precondition automaton at the node,
  `<prefix>pre_n_<state>`;
* `Symbol.pre_slot(j, state, type)`: the same component of the state of the j-th input child, kept as data of the
  parent, `<prefix>pre_s<j>_<state>` (`analysis/constraints/pre.py`);
* `Symbol.post_node(state, type)`, `Symbol.post_child(j, state, type)`, `Symbol.post_trail(p, i, state, type)`: the
  states of A¬post (`analysis/constraints/post.py`), `<prefix>post_n_<state>`, `<prefix>post_s<j>_<state>`,
  `<prefix>post_t<p>_<i>_<state>`;
* `Symbol.error(n)`: the error flag of a node after its first n children are collected, `<prefix>e<n>`
  (`ConstraintsBuilder.error_constraints`, `edge_error_constraints`).

`<prefix>` is `prefix_of(role)`; no role gives the bare names (`v<id>_<i>`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from treehornx import smt
from treehornx.intern import intern


@dataclass(frozen=True, slots=True)
class Parent:
    """The parent of a clause."""


@dataclass(frozen=True, slots=True)
class Slot:
    """The j-th child of a clause."""

    j: int


Role = Parent | Slot


def prefix_of(role: Role | None) -> str:
    """The prefix of the names of the symbols of a node with `role`: `p_`, `c<j>_`, or none."""
    match role:
        case None:
            return ""
        case Parent():
            return "p_"
        case Slot(j):
            return f"c{j}_"


@intern
@dataclass(slots=True, frozen=True)
class Symbol(smt.Var):
    base_name: str
    role: Role | None

    def __init__(self, base_name: str, type: smt.Type, role: Role | None):
        name = f"{prefix_of(role)}{base_name}"
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "type", type)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "base_name", base_name)

    if TYPE_CHECKING:

        @staticmethod
        def make(  # pyright: ignore[reportIncompatibleMethodOverride, reportImplicitOverride]
            *, base_name: str, type: smt.Type, role: Role | None
        ) -> Symbol: ...

    def with_role(self, role: Role | None) -> Symbol:
        if role == self.role:
            return self
        return Symbol.make(base_name=self.base_name, type=self.type, role=role)

    @staticmethod
    def variable(name: str, type: smt.Type, role: Role | None = None) -> Symbol:
        return Symbol.make(base_name=name, type=type, role=role)

    @staticmethod
    def local(id: int, index: int, type: smt.Type, role: Role | None = None) -> Symbol:
        base_name = f"v{id}_{index}"
        return Symbol.make(base_name=base_name, type=type, role=role)

    @staticmethod
    def field(id: int, index: int, type: smt.Type, role: Role | None = None) -> Symbol:
        """The data field `id` at the frame `index`."""
        return Symbol.make(base_name=f"f{id}_{index}", type=type, role=role)

    @staticmethod
    def pre_state(state: str, type: smt.Type, role: Role | None = None) -> Symbol:
        """A component of the state of the precondition automaton at the node."""
        return Symbol.make(base_name=f"pre_n_{state}", type=type, role=role)

    @staticmethod
    def pre_slot_state(j: int, state: str, type: smt.Type, role: Role | None = None) -> Symbol:
        """The same component of the state of the j-th input child, kept as data of the parent."""
        return Symbol.make(base_name=f"pre_s{j}_{state}", type=type, role=role)

    @staticmethod
    def post_state(state: str, type: smt.Type, role: Role | None = None) -> Symbol:
        """A component of the state of A¬post at the node."""
        return Symbol.make(base_name=f"post_n_{state}", type=type, role=role)

    @staticmethod
    def post_child_state(j: int, state: str, type: smt.Type, role: Role | None = None) -> Symbol:
        """A component of the state of A¬post at the j-th structural child."""
        return Symbol.make(base_name=f"post_s{j}_{state}", type=type, role=role)

    @staticmethod
    def post_trail_state(p: int, i: int, state: str, type: smt.Type, role: Role | None = None) -> Symbol:
        """A component of the state of A¬post carried by the trail of the pointer `p` at the frame `i`."""
        return Symbol.make(base_name=f"post_t{p}_{i}_{state}", type=type, role=role)

    @staticmethod
    def error(n: int, role: Role | None = None) -> Symbol:
        """The error flag of a node after its first `n` children are collected (`e<n>`). It is not an argument of
        `ConstrTLab.args`: `ConstrTLab.apply` adds it, so the phases never touch it."""
        return Symbol.make(base_name=f"e{n}", type=smt.Type.Bool, role=role)
