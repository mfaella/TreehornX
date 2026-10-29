"""Tree-shape layer: the automaton runs over the tainted labels and the error flag marks the output heaps that are
not trees (`enum_models/Taint/shape.py`, POPL27 Fig. 9).

The data constraints and the input tree are those of the Lab labels (as in `PreRunner`); the taints split a Lab
label into several node states. Errors of a node are its shape errors; errors of a link between a parent and its
child raise the flag of the parent. The runs ending in a memory error are not in the system
(`TaintingEngine.lab_finals`): memory safety is assumed.
"""

from dataclasses import dataclass, field

from typing_extensions import override

from treehornx.chc.Lab.clauses import consistency_constraint, label_constraints
from treehornx.chc.Lab.symbols import ChcLabUtils
from treehornx.chc.pre.runner import BotUpAutomataRunner
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab.initial import is_initial
from treehornx.enum_models.Taint import TaintedLabel, TaintingEngine
from treehornx.enum_models.Taint.shape import label_errors, pair_errors


@dataclass
class TreeShapeRunner(BotUpAutomataRunner[TaintedLabel]):
    sym: ChcLabUtils = field(kw_only=True)
    n: int = field(kw_only=True)
    engine: TaintingEngine = field(kw_only=True)
    name: str = "TreeShape"

    @override
    def node_data_symbols(self, label: TaintedLabel, prefix: str) -> list[sx.Var]:
        return self.sym.label_symbols(label.lab, prefix)

    @override
    def node_data_types(self, label: TaintedLabel) -> list[sx.Type]:
        return [t for _ in self.sym.kept_frames(label.lab) for t in self.sym.frame_types()]

    @override
    def node_field_symbol(self, field_id: int, index: int, prefix: str) -> sx.Var:
        return self.sym.field_symbol(field_id, index, prefix)

    @override
    def node_consistency(
        self, parent: TaintedLabel, child: TaintedLabel, j: int, parent_prefix: str, child_prefix: str
    ) -> list[sx.SExpr]:
        return consistency_constraint(self.sym, parent.lab, child.lab, j, parent_prefix, child_prefix)

    @override
    def node_local_constraints(self, label: TaintedLabel, prefix: str) -> list[sx.SExpr]:
        return label_constraints(self.sym, label.lab, prefix)

    @override
    def is_error(self, label: TaintedLabel, prefix: str) -> sx.SExpr:
        return sx.Constant(bool(label_errors(self.engine, label)))

    @override
    def is_pair_error(
        self, parent: TaintedLabel, child: TaintedLabel, j: int, parent_prefix: str, child_prefix: str
    ) -> sx.SExpr:
        return sx.Constant(bool(pair_errors(self.engine, Pair(parent, child, j))))

    @override
    def is_input_node(self, label: TaintedLabel) -> bool:
        return label.lab[1].active

    @override
    def is_input_child(self, parent: TaintedLabel, j: int) -> bool:
        return parent.lab[1].active_child[j]

    @override
    def is_root(self, label: TaintedLabel) -> bool:
        return is_initial(label.lab)
