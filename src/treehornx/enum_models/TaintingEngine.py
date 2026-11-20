"""Symbolic engine for the tainting of POPL27 (Sec. 6.1, Rules 1–5 of Fig. 5, CHCs T0–T5 of Fig. 7).

The engine runs over the final labels and pairs of a fixed `LabEngine` without the runs ending in a memory error
(`lab_finals`: memory safety is assumed). Every final label is a `TLab` with no taint (T0), and
the label holding the end of the lace starts the trail of the root pointer p̂ (T1). The steps then propagate the
taints:

* `step_int`  inside a label: the node gets tainted by the trails ending on it (T5) and a tainted node starts
              a trail for every final ⟨pf := p⟩ event of its log (T3);
* `step_down` from a parent to its j-th child: structural child tainting (T2) and the trails going down (T4);
* `step_up`   from the j-th child to its parent: the trails going up (T4).

Unlike the paper, a trail does not walk the lace frame by frame: like the rewind of CAV25, the trail of p at
(σ, i2) jumps to i_upd = last_upd(σ, i2, p) and continues on the frame linked to σ^{i_upd} by its prev link.
It ends where p points to the node (`points_here`). Every step propagates all the taints it can at once, and
fails (returns None) when the taints do not change. Taints are merged by join in ⊥ < ⊤ < ⊤+.

`finals` (the generic one of `SymbolicEngine`) keeps the labels and pairs on which no step changes the taints and
that compose a whole tree from a root.
"""

from dataclasses import dataclass, replace
from functools import cached_property
from typing import Iterable, Iterator

from typing_extensions import override

from treehornx.enum_models.SymbolicEngine import SymbolicExecutionEngine
from treehornx.enum_models.enviroment import Env, global_env
from treehornx.enum_models.helpers import (
    end_of_lace,
    field_trails,
    is_pfield_implicit,
    points_here,
    trail_down,
    trail_up,
)
from treehornx.enum_models.labels import TLab
from treehornx.enum_models.tainting import BoolPlus, TaintPtrCoord, TaintPtr
from treehornx.symbolic_tree import Edge, SymbolicTree


def initial_taints(label: TLab, env: Env = global_env()) -> TLab:
    """T0, and T1 when the lace ends in the label and p̂ is not nil there."""
    lab = label.lab
    root = env.func.ROOT
    taint_ptr = TaintPtr()
    if end_of_lace(lab, env) and not lab.frame.isnil[root]:
        taint_ptr = taint_ptr.set((root, len(lab)), BoolPlus.TopPlus)
    return TLab.make(taint_node=BoolPlus.Bottom, taint_ptr=taint_ptr, lab=lab)


@dataclass(init=False)
class TaintingEngine(SymbolicExecutionEngine):
    env: Env = global_env() # noqa: RUF009

    @cached_property
    def child_fields(self) -> tuple[int, ...]:
        return tuple(range(self.env.k + self.env.m))

    @property
    def root(self) -> int:
        return self.env.func.ROOT

    def initial(self, label: TLab) -> TLab:
        """T0, and T1 when the lace ends in the label and p̂ is not nil there."""
        return initial_taints(label, self.env)

    @classmethod
    def from_lab(cls, lab_tree: SymbolicTree[TLab], env: Env = global_env()) -> "TaintingEngine":
        """The engine over the final labels of a `LabEngine`, each with its initial taints (T0, T1)."""
        engine = cls(lab_tree.map(lambda _, label: initial_taints(label, env)))
        engine.env = env
        return engine

    # -----------------------------------------------------------------------
    # SymbolicEngine interface
    # -----------------------------------------------------------------------

    @override
    def step_int(self, label: TLab) -> Iterable[TLab] | None:
        """T5 and T3 up to their local fixpoint."""
        sigma = label.lab
        taint_node, taint_ptr = label.taint_node, label.taint_ptr
        while True:
            new_node, new_ptr = taint_node, taint_ptr
            # T5: end of pointer tainting
            if sigma.frame.active:
                for (p, i), v in taint_ptr.items():
                    if points_here(sigma, i, p):
                        new_node = new_node.join(v)
            # T3: start of pointer tainting
            if new_node:
                for key in field_trails(sigma, self.child_fields):
                    new_ptr = new_ptr.join(key, BoolPlus.Top)
            if new_node == taint_node and new_ptr == taint_ptr:
                break
            taint_node, taint_ptr = new_node, new_ptr
        new_label = TLab.make(taint_node=taint_node, taint_ptr=taint_ptr, lab=sigma)
        if new_label == label:
            return None
        return [new_label]

    def jumps_up(self, pair: Edge[TLab]) -> Iterator[tuple[TaintPtrCoord, BoolPlus]]:
        """The trails of the j-th child continuing on the parent: the key they reach there and their value."""
        for _, key, v in trail_up(pair.parent, pair.child, pair.j):
            yield key, v

    def jumps_down(self, pair: Edge[TLab]) -> Iterator[tuple[TaintPtrCoord, BoolPlus]]:
        """The trails of the parent continuing on its j-th child: the key they reach there and their value."""
        for _, key, v in trail_down(pair.parent, pair.child, pair.j):
            yield key, v

    def is_structural_child(self, pair: Edge[TLab]) -> bool:
        """child_is_dflt(σ, j) for a pointer field j: at the end, the j-th field of the parent is still the input
        child (nil when the parent had none). The parent field has no structural child."""
        return pair.j in self.child_fields and is_pfield_implicit(pair.parent.lab, len(pair.parent.lab), pair.j)

    @override
    def step_up(self, pair: Edge[TLab]) -> Edge[TLab] | None:
        """T4 from the j-th child to the parent, for every trail of the child."""
        parent = pair.parent
        taint_ptr = parent.taint_ptr
        for key, v in self.jumps_up(pair):
            taint_ptr = taint_ptr.join(key, v)
        if taint_ptr == parent.taint_ptr:
            return None
        return replace(
            pair, parent=TLab.make(taint_node=parent.taint_node, taint_ptr=taint_ptr, lab=parent.lab)
        )

    @override
    def step_down(self, pair: Edge[TLab]) -> Edge[TLab] | None:
        """T2 and T4 from the parent to its j-th child, for every trail of the parent."""
        parent, child = pair.parent, pair.child
        taint_node, taint_ptr = child.taint_node, child.taint_ptr
        # T2: structural child tainting
        if parent.taint_node and self.is_structural_child(pair) and child.lab.frame.active:
            taint_node = taint_node.join(BoolPlus.Top)
        # T4: pointer tainting propagation
        for key, v in self.jumps_down(pair):
            taint_ptr = taint_ptr.join(key, v)
        new_child = TLab.make(taint_node=taint_node, taint_ptr=taint_ptr, lab=child.lab)
        if new_child == child:
            return None
        return replace(pair, child=new_child)
