"""Symbolic engine for the tainting of POPL27 (Sec. 6.1, Rules 1–5 of Fig. 5, CHCs T0–T5 of Fig. 7).

The engine runs over the final labels and pairs of a fixed `LabEngine`: every final label is lifted to a
`TaintedLabel` with no taint (T0), and the label holding the end of the lace starts the trail of the root
pointer p̂ (T1). The steps then propagate the taints:

* `step_int`  inside a label: the node gets tainted by the trails ending on it (T5) and a tainted node starts
              a trail for every final ⟨pf := p⟩ event of its log (T3);
* `step_down` from a parent to its j-th child: structural child tainting (T2) and the trails going down (T4);
* `step_up`   from the j-th child to its parent: the trails going up (T4).

Unlike the paper, a trail does not walk the lace frame by frame: like the rewind of CAV25, the trail of p at
(σ, i2) jumps to i_upd = last_upd(σ, i2, p) and continues on the frame linked to σ^{i_upd} by its prev link.
It ends where p points to the node (`points_here`). Every step propagates all the taints it can at once, and
fails (returns None) when the taints do not change. Taints are merged by join in ⊥ < ⊤ < ⊤+.

`finals` keeps the saturated labels and pairs (no step changes them) that compose a whole tree from a root.
"""

from dataclasses import dataclass, replace
from typing import Iterable, Iterator

from typing_extensions import override

from treehornx.enum_models.core.Dir import Down, Up
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.core.SymbolicEngine import SymbolicEngine
from treehornx.enum_models.Lab.helpers import down_links, is_pfield_implicit, points_here, up_links
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.enum_models.Lab.Lab import Lab
from treehornx.enum_models.Lab.LabEngine import LabEngine
from treehornx.enum_models.Taint.BoolPlus import BoolPlus
from treehornx.enum_models.Taint.finals import saturated_finals
from treehornx.enum_models.Taint.helpers import field_trails, trail_origin
from treehornx.enum_models.Taint.TaintedLabel import TaintedLabel
from treehornx.enum_models.Taint.TaintPtr import Key, TaintPtr


@dataclass(init=False)
class TaintingEngine(SymbolicEngine[TaintedLabel]):
    lab_engine: LabEngine

    def __init__(self, lab_engine: LabEngine):
        self.lab_engine = lab_engine
        final_labels, final_pairs = lab_engine.finals()
        lifted = {lab: self.initial(lab) for lab in final_labels}
        init_pairs = {Pair(lifted[pair.parent], lifted[pair.child], pair.j) for pair in final_pairs}
        super().__init__(k=lab_engine.k, m=lab_engine.m, initial_pairs=init_pairs, start_states=set(lifted.values()))

    @property
    def root(self) -> int:
        return self.lab_engine.function.ROOT

    def initial(self, lab: Lab) -> TaintedLabel:
        """T0, and T1 when the lace ends in lab and p̂ is not nil there."""
        taint_ptr = TaintPtr()
        if self.lab_engine.is_end_of_lace(lab) and not lab.frame.isnil[self.root]:
            taint_ptr = taint_ptr.set((self.root, len(lab)), BoolPlus.TopPlus)
        return TaintedLabel(BoolPlus.Bottom, taint_ptr, lab)

    # -----------------------------------------------------------------------
    # SymbolicEngine interface
    # -----------------------------------------------------------------------

    @override
    def step_int(self, label: TaintedLabel) -> Iterable[TaintedLabel] | None:
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
                for key in field_trails(sigma, self.k):
                    new_ptr = new_ptr.join(key, BoolPlus.Top)
            if new_node == taint_node and new_ptr == taint_ptr:
                break
            taint_node, taint_ptr = new_node, new_ptr
        new_label = TaintedLabel(taint_node, taint_ptr, sigma)
        if new_label == label:
            return None
        return [new_label]

    def links_up(self, pair: Pair[TaintedLabel]) -> Iterator[tuple[Key, Key, BoolPlus]]:
        """The trails of the j-th child continuing on the parent: the key in the child, the key they reach in the
        parent and their value."""
        sigma, tau, j = pair.parent.lab, pair.child.lab, pair.j
        for (p, c), v in pair.child.taint_ptr.items():
            origin = trail_origin(tau, c, p)
            if origin is None or origin[1] != Up():
                continue
            i1 = next((i for i, c_ in down_links(sigma, tau, j) if c_ == origin[0]), None)
            if i1 is not None:
                yield (p, c), (p, i1), v

    def links_down(self, pair: Pair[TaintedLabel]) -> Iterator[tuple[Key, Key, BoolPlus]]:
        """The trails of the parent continuing on its j-th child: the key in the parent, the key they reach in the
        child and their value."""
        sigma, tau, j = pair.parent.lab, pair.child.lab, pair.j
        for (p, i2), v in pair.parent.taint_ptr.items():
            origin = trail_origin(sigma, i2, p)
            if origin is None or origin[1] != Down(j):
                continue
            b = next((c for i, c in up_links(sigma, tau, j) if i == origin[0]), None)
            if b is not None:
                yield (p, i2), (p, b), v

    def jumps_up(self, pair: Pair[TaintedLabel]) -> Iterator[tuple[Key, BoolPlus]]:
        """The trails of the j-th child continuing on the parent: the key they reach there and their value."""
        for _, key, v in self.links_up(pair):
            yield key, v

    def jumps_down(self, pair: Pair[TaintedLabel]) -> Iterator[tuple[Key, BoolPlus]]:
        """The trails of the parent continuing on its j-th child: the key they reach there and their value."""
        for _, key, v in self.links_down(pair):
            yield key, v

    def is_structural_child(self, pair: Pair[TaintedLabel]) -> bool:
        """child_is_dflt(σ, j) for a pointer field j: at the end, the j-th field of the parent is still the input
        child (nil when the parent had none)."""
        return pair.j < self.k and is_pfield_implicit(pair.parent.lab, len(pair.parent.lab), pair.j)

    @override
    def step_up(self, pair: Pair[TaintedLabel]) -> Pair[TaintedLabel] | None:
        """T4 from the j-th child to the parent, for every trail of the child."""
        parent = pair.parent
        taint_ptr = parent.taint_ptr
        for key, v in self.jumps_up(pair):
            taint_ptr = taint_ptr.join(key, v)
        if taint_ptr == parent.taint_ptr:
            return None
        return replace(pair, parent=replace(parent, taint_ptr=taint_ptr))

    @override
    def step_down(self, pair: Pair[TaintedLabel]) -> Pair[TaintedLabel] | None:
        """T2 and T4 from the parent to its j-th child, for every trail of the parent."""
        parent, child = pair.parent, pair.child
        taint_node, taint_ptr = child.taint_node, child.taint_ptr
        # T2: structural child tainting
        if parent.taint_node and self.is_structural_child(pair) and child.lab.frame.active:
            taint_node = taint_node.join(BoolPlus.Top)
        # T4: pointer tainting propagation
        for key, v in self.jumps_down(pair):
            taint_ptr = taint_ptr.join(key, v)
        new_child = TaintedLabel(taint_node, taint_ptr, child.lab)
        if new_child == child:
            return None
        return replace(pair, child=new_child)

    def is_saturated_l(self, label: TaintedLabel) -> bool:
        """No internal step changes the taints of label."""
        return self.step_int(label) is None

    def is_saturated_p(self, pair: Pair[TaintedLabel]) -> bool:
        """Both labels are saturated and no step across the pair changes their taints."""
        return (
            self.is_saturated_l(pair.parent)
            and self.is_saturated_l(pair.child)
            and self.step_up(pair) is None
            and self.step_down(pair) is None
        )

    @override
    def consistent(self, pair: Pair[TaintedLabel]) -> bool:
        return True

    @override
    def is_end_of_computation(self, state: TaintedLabel) -> bool:
        return self.lab_engine.is_end_of_lace(state.lab)

    @override
    def finals(self) -> tuple[set[TaintedLabel], set[Pair[TaintedLabel]]]:
        """The saturated labels and pairs composing a whole tree from a root (see `saturated_finals`)."""
        sat_pairs = {pair for pair in self.pairs if self.is_saturated_p(pair)}
        states = [state for state in self.states if self.is_saturated_l(state)]
        return saturated_finals(
            states, sat_pairs, self.pair_parent_index, self.pair_child_index, lambda state: is_initial(state.lab)
        )
