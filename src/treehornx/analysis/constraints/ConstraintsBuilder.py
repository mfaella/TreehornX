"""ConstraintsBuilder: the symbols of the data of the labels and every constraint on them.

* Lab (CAV25, Fig. 3, restricted to the data part of the frames): the data of the frame at position `index` of a
  label are the symbols `<prefix>v<id>_<index>` for the data variable `id` and `<prefix>f<id>_<index>` for the data
  field `id` (`frame_symbols`; `label_symbols` gives those of every frame; the arguments of a predicate are
  chosen by `ConstrTLab.args`). `label_constraints` relates the frames of a label,
  `consistency_constraint` the frames of a parent and its child adjacent in the lace.
* Pre (`pre`, the precondition SDTA): the state of an input node (`label[1].active`) is `pre_n_<STATE>` and the
  state of its j-th input child `pre_s<j>_<STATE>` (`pre_symbols`). ψ on the input data fields (frame 1) and the
  states of the input children (nil for a child that is not an input node); at a root, ψ_F on the state of the node,
  or `accept_empty` when the input tree is empty (`pre_constraints`); the slot j of the parent holds the state of its
  j-th child (`pre_consistency`). The root predicate only reaches the query, so ψ_F restricts the query to accepted
  inputs.
* Post (`post`, the negated postcondition A¬post): the state of an output node (tainted and active) is
  `post_n_<STATE>`, of its j-th structural child `post_s<j>_<STATE>`, of the trail of p at the frame i
  `post_t<p>_<i>_<STATE>` (`post_symbols`). S1 (a trail ending on an output node carries the
  state of the node) and S4 (ψ of A¬post at every output node) are internal (`post_constraints`); S2 (the two keys of
  a trail jumping between a parent and its child carry the same state) and S3 (the slot of a structural child holds
  the state of the child) link a parent and a child (`post_consistency`).
* Error flag: `e<n>` (`Symbol.error`) is the flag of a node after its first n children are collected. It starts at
  the error of the label (`label_error`, `error_constraints`); collecting the j-th child adds the flag of the child
  and the error of the edge (`edge_error`, `edge_error_constraints`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Callable, ClassVar

from treehornx import ir
from treehornx import smt as sx
from treehornx.analysis.constraints.sdta.SDTAContext import SDTAContext
from treehornx.analysis.constraints.symbols import Slot, Parent, Role
from treehornx.analysis.constraints import symbols as sy
from treehornx.symbolic_tree import Edge
from treehornx.enum_models.enviroment import Env, global_env
from treehornx.enum_models.labels import ERR, Internal
from treehornx.enum_models.helpers import (
    are_equal_after_rewind,
    child_is_struct,
    field_is_nil,
    get_pfield_ptr,
    linked_frames,
    points_here,
)
from treehornx.enum_models.labels import Lab, TLab, is_initial
from treehornx.enum_models.tainting import TaintPtrCoord
from treehornx.enum_models.TaintingEngine import trail_down, trail_up
from treehornx.smt.preprocess import simplify
from treehornx.analysis.constraints.errors import EdgeError, LabelError, States, no_edge_error, no_label_error

def equal_states(left: States, right: States) -> list[sx.SExpr]:
    """Component-wise equality of two states of the same automaton."""
    return [sx.OpExpr.make(op=sx.Operator.EQ, args=(left[state], right[state])) for state in left]


@dataclass
class ConstraintsBuilder:
    pre: SDTAContext | None = None
    """The states of the precondition automaton, None without a precondition."""
    post: SDTAContext | None = None
    """The states of the negated postcondition automaton, None without a postcondition."""
    label_constraints_cache: dict[tuple[Lab, Role | None], tuple[sx.SExpr, ...]] = field(
        default_factory=dict[tuple[Lab, Role | None], tuple[sx.SExpr, ...]], compare=False, repr=False
    )
    env: Env = global_env() # noqa: RUF009
    """`label_constraints` of every (label, role), built on the entry of the label's prefix."""
    label_error: LabelError = field(default=no_label_error, kw_only=True, compare=False, repr=False)
    """The error of a single label, given the A¬post state of its node (`errors.py`)."""
    edge_error: EdgeError = field(default=no_edge_error, kw_only=True, compare=False, repr=False)
    """The error of an edge (parent, child, j), given the A¬post states of both nodes (`errors.py`)."""

    @cached_property
    def function(self) -> ir.Function:
        return self.env.func

    @cached_property
    def arity(self) -> int:
        """The number of children of a node: k child fields and m allocations."""
        return self.env.k + self.env.m

    # error flag --------------------------------------------------------------

    def error_states(self, label: TLab, role: Role | None = None) -> States:
        """The state given to the error functions: the A¬post state of an output node, empty otherwise."""
        if self.post is None or not self.has_post_node(label):
            return {}
        return self.post_node(role)

    def error_constraints(self, label: TLab, n: int, role: Role | None = None) -> list[sx.SExpr]:
        """`e<n> = label_error(label)`: the flag starts with the error of the label (n = 0 for a node with children,
        n = arity for a leaf)."""
        flag = sy.Symbol.error(n, role)
        error = self.label_error(label, self.error_states(label, role))
        return [sx.OpExpr.make(op=sx.Operator.EQ, args=(flag, error))]

    def edge_error_constraints(self, parent: TLab, child: TLab, j: int) -> list[sx.SExpr]:
        """`p_e<j+1> = (or p_e<j> c<j>_e<arity> edge_error(parent, child, j))`: collecting the j-th child adds its
        flag and the error of the edge to the flag of the parent."""
        error = sx.OpExpr.make(
            op=sx.Operator.OR,
            args=(
                sy.Symbol.error(j, Parent()),
                sy.Symbol.error(self.arity, Slot(j)),
                self.edge_error(
                    parent, self.error_states(parent, Parent()), child, self.error_states(child, Slot(j)), j
                ),
            ),
        )
        flag = sy.Symbol.error(j + 1, Parent())
        return [sx.OpExpr.make(op=sx.Operator.EQ, args=(flag, simplify(error)))]

    @cached_property
    def child_fields(self) -> tuple[int, ...]:
        """The pointer fields that are children of the output tree (all but the parent field)."""
        return self.function.node.pointer_fields_ids

    # symbols -----------------------------------------------------------------

    def smt_type(self, data_type: ir.DataType) -> sx.Type:
        match data_type:
            case ir.DataType.INT:
                return sx.Type.Int
            case ir.DataType.BOOL:
                return sx.Type.Bool

    def var_symbol(self, var_id: int, index: int, role: Role | None = None) -> sy.Symbol:
        return sy.Symbol.local(var_id, index, self.smt_type(self.function.data_var_type(var_id)), role)

    def var_symbols(self, index: int, role: Role | None) -> list[sy.Symbol]:
        return [self.var_symbol(v.id, index, role) for v in self.function.data_vars]

    def field_symbol(self, field_id: int, index: int, role: Role | None = None) -> sy.Symbol:
        return sy.Symbol.field(field_id, index, self.smt_type(self.function.data_field_type(field_id)), role)

    def field_symbols(self, index: int, role: Role | None = None) -> list[sy.Symbol]:
        return [self.field_symbol(f.id, index, role) for f in self.function.node.data_fields]

    def frame_symbols(self, index: int, role: Role | None = None) -> list[sy.Symbol]:
        return [*self.var_symbols(index, role), *self.field_symbols(index, role)]

    def label_symbols(self, label: Lab, role: Role | None = None) -> list[sy.Symbol]:
        """The data symbols of every frame of `label`, those dropped from the predicate's arguments included."""
        return [symbol for i in range(1, len(label) + 1) for symbol in self.frame_symbols(i, role)]

    _BINARY_OPS: ClassVar[dict[str, sx.Operator]] = {
        "+": sx.Operator.ADD,
        "-": sx.Operator.SUB,
        "*": sx.Operator.MUL,
        "/": sx.Operator.DIV,
        "%": sx.Operator.MOD,
        "<": sx.Operator.LT,
        "<=": sx.Operator.LE,
        ">": sx.Operator.GT,
        ">=": sx.Operator.GE,
        "==": sx.Operator.EQ,
        "&&": sx.Operator.AND,
        "||": sx.Operator.OR,
    }

    def expr_to_smt(self, expr: ir.DataExpr, index: int, role: Role | None = None) -> sx.SExpr:
        """`expr` with every data variable evaluated at the frame `index`."""
        match expr:
            case ir.Const(value, ir.DataType.BOOL):
                return sx.Constant.make(value=bool(value))
            case ir.Const(value, ir.DataType.INT):
                return sx.Constant.make(value=int(value))
            case ir.Var(var_id):
                return self.var_symbol(var_id, index, role)
            case ir.UnOp("-", operand):
                return sx.OpExpr.make(op=sx.Operator.SUB, args=(0, self.expr_to_smt(operand, index, role)))
            case ir.UnOp("!", operand):
                return sx.OpExpr.make(op=sx.Operator.NOT, args=(self.expr_to_smt(operand, index, role),))
            case ir.BinOp("!=", left, right):
                return sx.OpExpr.make(
                    op=sx.Operator.NOT,
                    args=(
                        sx.OpExpr.make(
                            op=sx.Operator.EQ,
                            args=(self.expr_to_smt(left, index, role), self.expr_to_smt(right, index, role)),
                        ),
                    ),
                )
            case ir.BinOp(op, left, right) if op in self._BINARY_OPS:
                return sx.OpExpr.make(
                    op=self._BINARY_OPS[op],
                    args=(self.expr_to_smt(left, index, role), self.expr_to_smt(right, index, role)),
                )
            case _:
                raise NotImplementedError(f"Unsupported data expression: {expr}")

    # Lab ---------------------------------------------------------------------

    def consistency_constraint(self, parent: Lab, child: Lab, j: int) -> list[sx.SExpr]:
        """The data variables agree on every pair of frames of the parent and its j-th child adjacent in the lace."""
        return [
            sx.OpExpr.make(op=sx.Operator.EQ, args=(left, right))
            for i, c in linked_frames(parent, child, j)
            for left, right in zip(self.var_symbols(i, Parent()), self.var_symbols(c, Slot(j)))
        ]

    def initial_constraints(self, role: Role | None = None) -> list[sx.SExpr]:
        """The root's second frame copies val from the first (CHC II)."""
        return [
            sx.OpExpr.make(op=sx.Operator.EQ, args=(f2, f1))
            for f2, f1 in zip(self.field_symbols(2, role), self.field_symbols(1, role))
        ]

    @staticmethod
    def _assign_cond_value(label: Lab, a: int, cond: ir.HeapCond) -> bool:
        """Value of the heap condition evaluated by the internal step leaving the frame label^a."""
        f = label[a]
        match cond:
            case ir.IsNil(p, neg):
                return f.isnil[p] != neg
            case ir.PtrEq(p, q, neg):
                if f.isnil[p] or f.isnil[q]:
                    return (f.isnil[p] == f.isnil[q]) != neg
                return are_equal_after_rewind(label.cut(a), a, p, q) != neg
            case ir.FieldIsNil(_, pfield, neg):
                # p points to the node holding label^a, otherwise the step dereferences nil or rewinds
                return field_is_nil(label.cut(a), a, pfield) != neg

    def psi_internal(self, label: Lab, role: Role | None = None) -> list[sx.SExpr]:
        """Data constraints of the internal step from label^{b-1} to the top frame label^b."""
        b = len(label)
        a = b - 1
        f_a, f_b = label[a], label[b]
        vars_value: dict[int, sx.SExpr] = {}
        fields_value: dict[int, sx.SExpr] = {}
        constraints: list[sx.SExpr] = []

        match self.function[f_a.pc]:
            case ir.AssignData(d, expr):
                vars_value[d] = self.expr_to_smt(expr, a, role)
            case ir.AssignCond(d, cond) if not isinstance(f_b.event, ERR):
                vars_value[d] = sx.Constant.make(value=self._assign_cond_value(label, a, cond))
            case ir.IfGoto(ir.DataCond(expr), target) if target != f_a.pc + 1:
                cond = self.expr_to_smt(expr, a, role)
                constraints.append(cond if f_b.pc == target else sx.OpExpr.make(op=sx.Operator.NOT, args=(cond,)))
            case ir.StoreDataField(_, field_id, value) if not isinstance(f_b.event, ERR):
                fields_value[field_id] = self.expr_to_smt(value, a, role)
            case ir.LoadDataField(d, _, field_id) if not isinstance(f_b.event, ERR):
                vars_value[d] = self.field_symbol(field_id, a, role)
            case _:
                pass

        for v in self.function.data_vars:
            value = vars_value.get(v.id, self.var_symbol(v.id, a, role))
            constraints.append(sx.OpExpr.make(op=sx.Operator.EQ, args=(self.var_symbol(v.id, b, role), value)))
        for fd in self.function.node.data_fields:
            value = fields_value.get(fd.id, self.field_symbol(fd.id, a, role))
            constraints.append(sx.OpExpr.make(op=sx.Operator.EQ, args=(self.field_symbol(fd.id, b, role), value)))
        return constraints

    def _local_constraints(self, label: Lab, role: Role | None) -> list[sx.SExpr]:
        """Constraints of the step reaching the top frame of `label`, if any.

        An internal step is constrained by ψ_internal; an external one (CHC IV/V) copies the data fields from the
        frame below in the same node, the data variables being copied by `consistency_constraint`."""
        b = len(label)
        if b == 1:
            return []
        if label.frame.prev != Internal():
            return [
                sx.OpExpr.make(op=sx.Operator.EQ, args=(f_b, f_below))
                for f_b, f_below in zip(self.field_symbols(b, role), self.field_symbols(b - 1, role))
            ]
        if b == 2 and is_initial(label):
            # (Internal(), 2) marks the second frame of the root, it is not a step of the program
            return self.initial_constraints(role)
        return self.psi_internal(label, role)

    def label_constraints(self, label: Lab, role: Role | None = None) -> list[sx.SExpr]:
        """Constraints of every step reaching a frame of `label`, including the frames dropped from its arguments.

        The frames dropped by the compression only occur here, so they are quantified variables of the clause."""
        cache = self.label_constraints_cache
        # walk back to the longest prefix already computed, then extend it frame by frame
        missing: list[Lab] = []
        current: Lab | None = label
        while current is not None and (current, role) not in cache:
            missing.append(current)
            current = current.prefix
        cached = () if current is None else cache[current, role]
        for prefix_label in reversed(missing):
            cached = cached + tuple(self._local_constraints(prefix_label, role))
            cache[prefix_label, role] = cached
        return list(cached)

    # Pre ---------------------------------------------------------------------

    def _pre(self) -> SDTAContext:
        assert self.pre is not None, "no precondition"
        return self.pre

    def _post(self) -> SDTAContext:
        assert self.post is not None, "no postcondition"
        return self.post

    @staticmethod
    def _states(ctx: SDTAContext, make: Callable[[str, sx.Type, Role | None], sy.Symbol], role: Role | None) -> States:
        """The state of `ctx` whose component `state` is the symbol `make(state, type, role)`."""
        return {
            state: make(state, sx.Type.Int if kind == "int" else sx.Type.Bool, role)
            for state, kind in ctx.states.items()
        }

    def is_input(self, label: TLab) -> bool:
        """`label` is the label of an input node."""
        return label.lab[1].active

    def input_slots(self, label: TLab) -> list[int]:
        """The child fields (the parent field excluded) whose child is an input node."""
        k, node, first = self.env.k, self.function.node, label.lab[1]
        return [j for j in range(k) if node.is_child_field(j) and first.active_child[j]]

    def pre_node(self, role: Role | None = None) -> States:
        """The state of the precondition automaton at the node."""
        return self._states(self._pre(), sy.Symbol.pre_state, role)

    def pre_slot(self, j: int, role: Role | None = None) -> States:
        """The state of the precondition automaton at the j-th input child, kept as data of the parent."""
        return self._states(self._pre(), lambda state, t, r: sy.Symbol.pre_slot_state(j, state, t, r), role)

    def pre_symbols(self, label: TLab, role: Role | None = None) -> list[sy.Symbol]:
        """The states of the precondition automaton of `label`: the node and its input children, none for a node
        that is not an input node."""
        if self.pre is None or not self.is_input(label):
            return []
        return [
            *self.pre_node(role).values(),
            *(s for j in self.input_slots(label) for s in self.pre_slot(j, role).values()),
        ]

    def pre_constraints(self, label: TLab, role: Role | None = None) -> list[sx.SExpr]:
        """ψ at an input node and ψ_F at a root, on the symbols of the TLab and the states."""
        if self.pre is None:
            return []
        ctx = self.pre
        constraints: list[sx.SExpr] = []
        node = self.function.node
        is_input = self.is_input(label)
        if is_input:
            slots = set(self.input_slots(label))
            children: dict[str, dict[str, sx.Var] | None] = {
                node.pointer_fields[j].name: (dict(self.pre_slot(j, role)) if j in slots else None)
                for j in range(self.env.k)
                if node.is_child_field(j)
            }
            fields = {f.name: self.field_symbol(f.id, 1, role) for f in node.data_fields}
            constraints.append(ctx.psi(children, fields, dict(self.pre_node(role))))
        if is_initial(label.lab):
            state =  dict(self.pre_node(role)) if is_input else None
            constraints.append(ctx.psiF(state))
        return constraints

    def pre_consistency(self, parent: TLab, child: TLab, j: int) -> list[sx.SExpr]:
        """The slot j of the parent holds the state of its j-th child."""
        if self.pre is None or not (self.is_input(parent) and j in self.input_slots(parent)):
            return []
        assert self.is_input(child), "the input child of a pair is not an input node"
        return equal_states(self.pre_slot(j, Parent()), self.pre_node(Slot(j)))

    # Post --------------------------------------------------------------------


    def has_post_node(self, label: TLab) -> bool:
        """`label` is the label of an output node (tainted and active)."""
        return bool(label.taint_node) and label.lab.frame.active

    def post_slots(self, label: TLab) -> list[int]:
        """The structural children of an output node."""
        if not self.has_post_node(label):
            return []
        return [j for j in self.child_fields if child_is_struct(label.lab, j, self.env.k)]

    def post_keys(self, label: TLab) -> list[TaintPtrCoord]:
        """The keys of the trails of `label`, in order."""
        return sorted(label.taint_ptr)

    def post_node(self, role: Role | None = None) -> States:
        """The state of A¬post at the node."""
        return self._states(self._post(), sy.Symbol.post_state, role)

    def post_slot(self, j: int, role: Role | None = None) -> States:
        """The state of A¬post at the j-th structural child, kept as data of the parent."""
        return self._states(self._post(), lambda state, t, r: sy.Symbol.post_child_state(j, state, t, r), role)

    def post_trail(self, key: TaintPtrCoord, role: Role | None = None) -> States:
        """The state of A¬post carried by the trail of the pointer `key[0]` at the frame `key[1]`."""
        p, i = key
        return self._states(self._post(), lambda state, t, r: sy.Symbol.post_trail_state(p, i, state, t, r), role)

    def post_symbols(self, label: TLab, role: Role | None = None) -> list[sy.Symbol]:
        """The states of A¬post of `label`: the node (an output node), its structural children, its trails."""
        if self.post is None:
            return []
        symbols: list[sy.Symbol] = list(self.post_node(role).values()) if self.has_post_node(label) else []
        for j in self.post_slots(label):
            symbols += self.post_slot(j, role).values()
        for key in self.post_keys(label):
            symbols += self.post_trail(key, role).values()
        return symbols

    def _post_psi(self, label: TLab, role: Role | None) -> sx.SExpr:
        """S4: ψ of A¬post at the output node of `label`."""
        ctx = self._post()
        sigma = label.lab
        children: dict[str, dict[str, sx.Var] | None] = {}
        for j in self.child_fields:
            pfield = self.function.node.pointer_fields[j]
            ptr = get_pfield_ptr(sigma, len(sigma), j)
            if child_is_struct(sigma, j, self.env.k):
                children[pfield.name] = dict(self.post_slot(j, role))
            elif ptr is not None:
                assert ptr in label.taint_ptr, f"the field {pfield.name} of a tainted node seeds no trail"
                children[pfield.name] = dict(self.post_trail(ptr, role))
            else:
                children[pfield.name] = None
        fields = {f.name: self.field_symbol(f.id, len(sigma), role) for f in self.function.node.data_fields}
        return ctx.psi(children, fields, dict(self.post_node(role)))

    def post_constraints(self, label: TLab, role: Role | None = None) -> list[sx.SExpr]:
        """S1 and S4 at `label`."""
        constraints: list[sx.SExpr] = []
        if self.post is not None and self.has_post_node(label):
            for key in self.post_keys(label):
                if points_here(label.lab, key[1], key[0]):
                    constraints += equal_states(self.post_trail(key, role), self.post_node(role))
            constraints.append(self._post_psi(label, role))
        return constraints

    def post_consistency(self, parent: TLab, child: TLab, j: int) -> list[sx.SExpr]:
        """S2 and S3 between `parent` and its j-th child."""
        if self.post is None:
            return []
        pair = Edge(parent, child, j)
        constraints: list[sx.SExpr] = []
        for child_key, parent_key, _ in trail_up(pair.parent, pair.child, pair.j):
            constraints += equal_states(self.post_trail(parent_key, Parent()), self.post_trail(child_key, Slot(j)))
        for parent_key, child_key, _ in trail_down(pair.parent, pair.child, pair.j):
            constraints += equal_states(self.post_trail(child_key, Slot(j)), self.post_trail(parent_key, Parent()))
        if j in self.post_slots(parent) and self.has_post_node(child):
            constraints += equal_states(self.post_slot(j, Parent()), self.post_node(Slot(j)))
        return constraints
