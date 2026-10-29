"""Postcondition layer: the negated postcondition automaton A¬post runs on the output tree (POPL27, Sec. 7, Fig. 10).

The runner is the tree-shape one (precondition, data constraints and input tree of the Lab labels) with the states of
A¬post added to the data of every tainted label (`symbols.py`). It assumes that the output heap is a tree, as the
tree-shape layer assumes memory safety, so the shape errors are not checked. The constraints are:

* S1: a trail ending on an output node carries the state of the node;
* S2: the two keys of a trail jumping between a parent and its child carry the same state;
* S3: the slot of a structural child holds the state of the child;
* S4: ψ of A¬post at every output node, on the states of its output children (child_state, App. E) and its final data.

The error flag is raised at the output root accepted by ψ_F (SQ1), or at the end of the lace when the output is empty
and A¬post accepts the empty tree (SQ2).
"""

from dataclasses import dataclass, field
from functools import cached_property

from typing_extensions import override

from treehornx.chc.Post.symbols import PostSymbols, equal_states
from treehornx.chc.pre.runner import disjunction
from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.chc.smt import sexpr as sx
from treehornx.chc.TreeShape.TreeShapeRunner import TreeShapeRunner
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab.helpers import get_pfield_ptr, points_here
from treehornx.enum_models.Taint import BoolPlus, TaintedLabel
from treehornx.enum_models.Taint.helpers import child_is_struct


@dataclass
class PostRunner(TreeShapeRunner):
    post: SDTAContext = field(kw_only=True)
    """The negated postcondition automaton: it accepts the output trees that violate the postcondition."""
    accept_empty_post: bool = field(default=False, kw_only=True)
    """ψ_F of A¬post on the nil state, checked when the output is empty."""
    name: str = "Post"

    @cached_property
    def post_sym(self) -> PostSymbols:
        return PostSymbols(self.post, self.k)

    @override
    def node_data_symbols(self, label: TaintedLabel, prefix: str) -> list[sx.Var]:
        return [*super().node_data_symbols(label, prefix), *self.post_sym.symbols(label, prefix)]

    @override
    def node_data_types(self, label: TaintedLabel) -> list[sx.Type]:
        return [*super().node_data_types(label), *self.post_sym.types(label)]

    def _post_psi(self, label: TaintedLabel, prefix: str) -> sx.SExpr:
        """S4: ψ of A¬post at the output node of `label`."""
        sym, sigma = self.post_sym, label.lab
        children: dict[str, dict[str, sx.Var] | None] = {}
        for j, pfield in enumerate(self.function.node.pointer_fields):
            ptr = get_pfield_ptr(sigma, len(sigma), j)
            if child_is_struct(sigma, j, self.k):
                children[pfield.name] = sym.slot(j, prefix)
            elif ptr is not None:
                assert ptr in label.taint_ptr, f"the field {pfield.name} of a tainted node seeds no trail"
                children[pfield.name] = sym.trail(ptr, prefix)
            else:
                children[pfield.name] = None
        fields = {f.name: self.node_field_symbol(f.id, len(sigma), prefix) for f in self.function.node.data_fields}
        return self.post.psi(children, fields, sym.node(prefix))

    @override
    def node_local_constraints(self, label: TaintedLabel, prefix: str) -> list[sx.SExpr]:
        constraints = super().node_local_constraints(label, prefix)
        sym = self.post_sym
        if sym.has_node_state(label):
            # S1: the trails ending on the node
            for key in sym.keys(label):
                if points_here(label.lab, key[1], key[0]):
                    constraints += equal_states(sym.trail(key, prefix), sym.node(prefix))
            constraints.append(self._post_psi(label, prefix))
        return constraints

    @override
    def node_consistency(
        self, parent: TaintedLabel, child: TaintedLabel, j: int, parent_prefix: str, child_prefix: str
    ) -> list[sx.SExpr]:
        constraints = super().node_consistency(parent, child, j, parent_prefix, child_prefix)
        sym, pair = self.post_sym, Pair(parent, child, j)
        # S2: the trails jumping across the pair
        for child_key, parent_key, _ in self.engine.links_up(pair):
            constraints += equal_states(sym.trail(parent_key, parent_prefix), sym.trail(child_key, child_prefix))
        for parent_key, child_key, _ in self.engine.links_down(pair):
            constraints += equal_states(sym.trail(child_key, child_prefix), sym.trail(parent_key, parent_prefix))
        # S3: the structural child
        if j in sym.slots(parent) and sym.has_node_state(child):
            constraints += equal_states(sym.slot(j, parent_prefix), sym.node(child_prefix))
        return constraints

    def is_output_root(self, label: TaintedLabel) -> bool:
        """The trail of p̂ (⊤+) ends on the node: it is the final value of the root pointer."""
        root = self.engine.root
        return any(
            v is BoolPlus.TopPlus and p == root and points_here(label.lab, i, p)
            for (p, i), v in label.taint_ptr.items()
        )

    def is_empty_output(self, label: TaintedLabel) -> bool:
        return self.engine.lab_engine.is_end_of_lace(label.lab) and label.lab.frame.isnil[self.engine.root]

    @override
    def is_error(self, label: TaintedLabel, prefix: str) -> sx.SExpr:
        # SQ1: the output tree is accepted by A¬post
        accepted = (
            self.post.psiF(self.post_sym.node(prefix))
            if self.post_sym.has_node_state(label) and self.is_output_root(label)
            else sx.FALSE
        )
        # SQ2: the output tree is empty and A¬post accepts it
        empty = sx.Constant(self.accept_empty_post and self.is_empty_output(label))
        return disjunction(accepted, empty)

    @override
    def is_pair_error(
        self, parent: TaintedLabel, child: TaintedLabel, j: int, parent_prefix: str, child_prefix: str
    ) -> sx.SExpr:
        # the output heap is assumed to be a tree
        return sx.FALSE
