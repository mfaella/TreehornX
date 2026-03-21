import json
from dataclasses import dataclass
from typing import Iterable

import graphviz as gv
from treehornx.enum_labels.core.Dir import Internal, Up
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label
from treehornx.enum_labels.knitter.Pair import Pair
from treehornx.enum_labels.knitter.StepKind import StepKind
from treehornx.enum_labels.LabelDB import LabelDB
from treehornx.enum_labels.PairDB import PairDB
from treehornx.ir.function import Function
from treehornx.ir.instructions import Return
from treehornx.report.format import frame_to_json


@dataclass
class DependencyGraphBuilder:
    function: Function
    labels: LabelDB
    pairs: PairDB

    def _label_name(self, label: Label) -> str:
        lab_id = self.labels.id(label)
        return f"Lab{lab_id}"

    def _create_label_node(self, graph: gv.Digraph, lab: Label):
        f = lab.frame
        fjson = frame_to_json(f)
        tooltip = json.dumps(fjson, indent=2)
        lab_name = self._label_name(lab)

        if self.labels.is_endless_loop_pivot(lab):
            graph.node(lab_name, style="filled", tooltip=tooltip, label=f"Loop()", fillcolor="red")
            return

        err_event = next((e for e in lab.frame.events if e in {ERR(), OOM(), LOF()}), None)
        if err_event:
            graph.node(lab_name, tooltip=tooltip, style="filled", label=f"{lab_name}:{err_event}", fillcolor="yellow")
            return

        if Exit() in lab.frame.events:
            graph.node(lab_name, tooltip=tooltip, style="filled", label=f"{lab_name}:Exit()", fillcolor="lightgreen")
            return

        if lab.origin is None:
            graph.node(lab_name, label=f"{lab_name}", tooltip=tooltip, style="filled", fillcolor="white")
        else:
            pc = lab.frame.pc
            instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
            graph.node(lab_name, label=f"{lab_name}\n{instr}", tooltip=tooltip, style="filled", fillcolor="white")

    def _continuity_pairs(self) -> Iterable[Pair]:
        return (
            p
            for p in self.pairs
            if (leader := p.leader()).frame.prev is not None and leader.frame.prev[0] == Internal()
        )

    def add_lace_internal_step_dependency(self, prev: Label, next: Label, graph: gv.Digraph):
        self.add_label_node(graph, prev)
        self.add_label_node(graph, next)
        prev_name = self._label_name(prev)
        next_name = self._label_name(next)
        graph.edge(prev_name, next_name, label="I", color="blue")

    def add_structural_internal_step_dependency(self, prev: Label, next: Label, graph: gv.Digraph):
        self.add_label_node(graph, prev)
        self.add_label_node(graph, next)
        prev_name = self._label_name(prev)
        next_name = self._label_name(next)
        graph.edge(prev_name, next_name, label="I", color="grey")

    def add_external_step_dependency(self, pair: Pair, graph: gv.Digraph):
        sigma = pair.follower()
        tau = pair.leader()
        self._create_label_node(graph, tau)
        self._create_label_node(graph, sigma)
        tau_name = self._label_name(tau)
        sigma_name = self._label_name(sigma)
        external_step_label = f"{f'D({pair.child_key})' if pair.dir() == Up() else 'U'}"
        graph.edge(sigma_name, tau_name, label=external_step_label, color="blue")

    def full_dependency_graph(self) -> gv.Digraph:
        graph = gv.Digraph("full dependency graph", strict=True)
        graph.attr(bgcolor="lightgrey", style="filled")

        for pair in self._continuity_pairs():
            leader = pair.leader()
            follower = pair.follower()
            if leader.frame.prev is not None and leader.frame.prev[0] == Internal():
                for ancestor in self.labels.ancestors(leader):
                    self.add_lace_internal_step_dependency(leader, ancestor, graph)
            elif leader.frame.prev is not None and follower.frame.index != 0:
                self.add_external_step_dependency(pair, graph)
                self.add_structural_internal_step_dependency(leader, follower, graph)

        return graph

    def compressed_dependency_graph(self) -> gv.Digraph:
        graph = gv.Digraph("compressed dependency graph", strict=True)
        graph.attr(bgcolor="lightgrey", style="filled")

        for pair in self._continuity_pairs():
            if pair.last_step_kind() != StepKind.EXTERNAL:
                continue
            leader = pair.leader()
            follower = pair.follower()

            self.add_external_step_dependency(pair, graph)

            match leader.frame.prev:
                case (Internal(), _):
                    self.add_lace_internal_step_dependency(follower.origin, follower, graph)
                case (_, _):
                    self.add_structural_internal_step_dependency(follower.origin, follower, graph)
                case _:
                    pass

        return graph

    def internal_dependency_graph(self, path: str):
        graph = gv.Digraph("consecutive internal dependency graph", strict=True)
        graph.attr(bgcolor="lightgrey", style="filled")

        for label in self.labels:
            match label.frame.prev:
                case (Internal(), _):
                    for ancestor in self.labels.ancestors(label):
                        self.add_lace_internal_step_dependency(label, ancestor, graph)
                case _ if label.origin is not None:
                    self.add_structural_internal_step_dependency(label, label.origin, graph)
                case _:
                    pass

        return graph
