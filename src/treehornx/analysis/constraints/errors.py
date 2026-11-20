"""The error functions of the checks, given to `ConstraintsBuilder` as `label_error` and `edge_error`.

* `label_error(label, states)`: the error of a single label. `states` is the state of A¬post at the node
  (`ConstraintsBuilder.post_node`, named for the role of the node in the clause), empty when there is no
  postcondition or the node is not an output node.
* `edge_error(parent, parent_states, child, child_states, j)`: the error of the edge between `parent` and its j-th
  child `child`, with the states of both nodes.

The checks:

* memory (`memory_label_error`): the lace ends with one of the exit codes (ERR, OOM, label overflow);
* tree shape (`shape_label_error`, `shape_edge_error`): the shape errors of the taints (`enum_models/shape.py`,
  POPL27 Fig. 9);
* postcondition (`post_label_error`): A¬post accepts the output tree at its root (SQ1), or the output is empty and
  A¬post accepts the empty tree (SQ2). The output heap is assumed to be a tree, so no edge is an error.
"""

from __future__ import annotations

from typing import Callable, Iterable

from treehornx import smt as sx
from treehornx.analysis.constraints.sdta.SDTAContext import SDTAContext
from treehornx.analysis.constraints.symbols import Symbol
from treehornx.symbolic_tree import Edge
from treehornx.enum_models.enviroment import Env, global_env
from treehornx.enum_models.helpers import end_of_lace, label_exit, points_here
from treehornx.enum_models.labels import ExitCode, TLab
from treehornx.enum_models.shape import label_errors, pair_errors
from treehornx.enum_models.tainting import BoolPlus
from treehornx.enum_models.TaintingEngine import TaintingEngine
from treehornx.smt.preprocess import simplify


States = dict[str, Symbol]
"""A state of an automaton: one symbol per component, by component name."""

LabelError = Callable[[TLab, States], sx.SExpr]
EdgeError = Callable[[TLab, States, TLab, States, int], sx.SExpr]


def no_label_error(label: TLab, states: States) -> sx.SExpr:
    return sx.FALSE


def no_edge_error(parent: TLab, parent_states: States, child: TLab, child_states: States, j: int) -> sx.SExpr:
    return sx.FALSE


# memory ----------------------------------------------------------------------


def memory_label_error(exit_codes: Iterable[ExitCode] = (ExitCode.E,), env: Env = global_env()) -> LabelError:
    """The lace ends in the label with one of `exit_codes` (E: error, M: out of memory, O: label overflow)."""
    codes = frozenset(exit_codes)

    def error(label: TLab, states: States) -> sx.SExpr:
        return sx.Constant.make(value=label_exit(label.lab, env) in codes)

    return error


# tree shape ------------------------------------------------------------------


def shape_label_error(engine: TaintingEngine) -> LabelError:
    """The node of the label has a shape error (`shape.label_errors`)."""

    def error(label: TLab, states: States) -> sx.SExpr:
        return sx.Constant.make(value=bool(label_errors(engine, label)))

    return error


def shape_edge_error(engine: TaintingEngine) -> EdgeError:
    """The edge has a shape error (`shape.pair_errors`)."""

    def error(parent: TLab, parent_states: States, child: TLab, child_states: States, j: int) -> sx.SExpr:
        return sx.Constant.make(value=bool(pair_errors(engine, Edge(parent, child, j))))

    return error


# postcondition ---------------------------------------------------------------


def is_output_root(engine: TaintingEngine, label: TLab) -> bool:
    """The trail of p̂ (TopPlus) ends on the node: the node is the final value of the root pointer."""
    root = engine.root
    return any(
        value is BoolPlus.TopPlus and p == root and points_here(label.lab, i, p)
        for (p, i), value in label.taint_ptr.items()
    )


def is_empty_output(engine: TaintingEngine, label: TLab) -> bool:
    """The lace ends in the label and the root pointer is nil there."""
    lab = label.lab
    return end_of_lace(lab, engine.env) and lab.frame.isnil[engine.root]


def post_label_error(engine: TaintingEngine, post: SDTAContext, accept_empty: bool = False) -> LabelError:
    """SQ1: ψ_F of A¬post on the state of the output root. SQ2: the output is empty and `accept_empty` (A¬post
    accepts the empty tree)."""

    def error(label: TLab, states: States) -> sx.SExpr:
        accepted = post.psiF(dict(states)) if states and is_output_root(engine, label) else sx.FALSE
        empty = sx.Constant.make(value=accept_empty and is_empty_output(engine, label))
        return simplify(sx.OpExpr.make(op=sx.Operator.OR, args=(accepted, empty)))

    return error
