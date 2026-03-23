import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import pydot
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


class DependencyGraphKind(Enum):
    FULL = "full"
    COMPRESSED = "compressed"
    INTERNAL = "internal"
    COMPRESSED_INTERNAL = "compressed_internal"


@dataclass(slots=True)
class DependencyGraphInfo:
    kind: DependencyGraphKind
    nodes_count: int


@dataclass
class DependencyGraphBuilder:
    function: Function
    labels: LabelDB
    pairs: PairDB
    internal_dependency_graph_nodes_count: int = field(init=False, default=0)
    compressed_internal_dependency_graph_nodes_count: int = field(init=False, default=0)
    compressed_dependency_graph_nodes_count: int = field(init=False, default=0)
    full_dependency_graph_nodes_count: int = field(init=False, default=0)

    def _label_name(self, label: Label) -> str:
        lab_id = self.labels.id(label)
        return f"Lab{lab_id}"

    def _create_label_node(self, graph: pydot.Dot, lab: Label):
        lab_name = self._label_name(lab)
        if graph.get_node(lab_name):
            return
        f = lab.frame
        fjson = frame_to_json(f)
        tooltip = json.dumps(fjson, indent=2)

        if self.labels.is_endless_loop_pivot(lab):
            node = pydot.Node(lab_name, style="filled", tooltip=tooltip, label=f"Loop()", fillcolor="red")
            graph.add_node(node)
            return

        err_event = next((e for e in lab.frame.events if e in {ERR(), OOM(), LOF()}), None)
        if err_event:
            node = pydot.Node(
                lab_name, tooltip=tooltip, style="filled", label=f"{lab_name}:{err_event}", fillcolor="yellow"
            )
            graph.add_node(node)
            return

        if Exit() in lab.frame.events:
            node = pydot.Node(
                lab_name, tooltip=tooltip, style="filled", label=f"{lab_name}:Exit()", fillcolor="lightgreen"
            )
            graph.add_node(node)
            return

        if lab.origin is None:
            node = pydot.Node(lab_name, label=f"{lab_name}", tooltip=tooltip, style="filled", fillcolor="white")
            graph.add_node(node)
        else:
            pc = lab.frame.pc
            instr = self.function.instructions[pc] if pc < len(self.function.instructions) else Return()
            node = pydot.Node(
                lab_name, label=f"{lab_name}\n{instr}", tooltip=tooltip, style="filled", fillcolor="white"
            )
            graph.add_node(node)

    def _engine(self) -> str:
        return "dot"

    def _continuity_pairs(self) -> Iterable[Pair]:
        return (
            p
            for p in self.pairs
            if (leader := p.leader()).frame.prev is not None
            and (leader.frame.prev[0] == Internal() or leader.frame.prev[0] == p.dir())
        )

    def add_lace_internal_step_dependency(self, prev: Label, next: Label, graph: pydot.Dot):
        self._create_label_node(graph, prev)
        self._create_label_node(graph, next)
        prev_name = self._label_name(prev)
        next_name = self._label_name(next)
        edge = pydot.Edge(prev_name, next_name, label="I", color="blue")
        graph.add_edge(edge)

    def add_structural_internal_step_dependency(self, prev: Label, next: Label, graph: pydot.Dot):
        self._create_label_node(graph, prev)
        self._create_label_node(graph, next)
        prev_name = self._label_name(prev)
        next_name = self._label_name(next)
        edge = pydot.Edge(prev_name, next_name, color="grey")
        graph.add_edge(edge)

    def add_external_step_dependency(self, pair: Pair, graph: pydot.Dot):
        sigma = pair.follower()
        tau = pair.leader()
        self._create_label_node(graph, tau)
        self._create_label_node(graph, sigma)
        tau_name = self._label_name(tau)
        sigma_name = self._label_name(sigma)
        external_step_label = f"{f'D({pair.child_key})' if pair.dir() == Up() else 'U'}"
        edge = pydot.Edge(sigma_name, tau_name, label=external_step_label, color="blue")
        graph.add_edge(edge)

    def _make_graph(self, graph_name: str) -> pydot.Dot:
        engine = self._engine()
        graph = pydot.Dot(graph_name, type="digraph", style="filled", bgcolor="lightgrey", strict=True, engine=engine)
        return graph

    def full_dependency_graph(self) -> pydot.Dot:
        graph = self._make_graph("full dependency graph")

        for pair in self._continuity_pairs():
            leader = pair.leader()
            follower = pair.follower()
            if leader.frame.prev is not None:
                if leader.frame.prev[0] == Internal():
                    for ancestor in self.labels.ancestors(leader):
                        self.add_lace_internal_step_dependency(ancestor, leader, graph)
                else:
                    self.add_external_step_dependency(pair, graph)
                    self.add_structural_internal_step_dependency(leader.origin, leader, graph)

        return graph

    def compressed_dependency_graph(self) -> pydot.Dot:
        graph = self._make_graph("compressed dependency graph")

        for pair in self._continuity_pairs():
            leader = pair.leader()
            follower = pair.follower()
            if pair.last_step_kind() == StepKind.EXTERNAL:
                self.add_external_step_dependency(pair, graph)

                match leader.frame.prev:
                    case (_, _):
                        self.add_structural_internal_step_dependency(leader.origin, leader, graph)
                    case _:
                        pass

                match follower.frame.prev:
                    case (Internal(), _):
                        self.add_lace_internal_step_dependency(follower.origin, follower, graph)
                    case (_, _):
                        self.add_structural_internal_step_dependency(follower.origin, follower, graph)
                    case _:
                        pass
            elif any(e in leader.frame.events for e in (Exit(), ERR(), OOM(), LOF())):
                self.add_lace_internal_step_dependency(leader.origin, leader, graph)

        return graph

    def internal_dependency_graph(self) -> pydot.Dot:
        graph = self._make_graph("internal dependency graph")

        for label in self.labels:
            match label.frame.prev:
                case (Internal(), _):
                    for ancestor in self.labels.ancestors(label):
                        self.add_lace_internal_step_dependency(ancestor, label, graph)
                case _ if label.origin is not None:
                    self.add_structural_internal_step_dependency(label.origin, label, graph)
                case _:
                    pass

        return graph

    def compressed_internal_dependency_grpah(self) -> pydot.Dot:
        graph = self._make_graph("compressed internal dependency graph")

        for pair in self._continuity_pairs():
            leader = pair.leader()
            follower = pair.follower()
            if pair.last_step_kind() == StepKind.EXTERNAL:
                match leader.frame.prev:
                    case (_, _):
                        self.add_structural_internal_step_dependency(leader.origin, leader, graph)
                    case _:
                        pass

                match follower.frame.prev:
                    case (Internal(), _):
                        self.add_lace_internal_step_dependency(follower.origin, follower, graph)
                    case (_, _):
                        self.add_structural_internal_step_dependency(follower.origin, follower, graph)
                    case _:
                        pass
            elif any(e in leader.frame.events for e in (Exit(), ERR(), OOM(), LOF())):
                self.add_lace_internal_step_dependency(leader.origin, leader, graph)

        return graph

    def dependency_graph(self, kind: DependencyGraphKind) -> pydot.Dot:
        match kind:
            case DependencyGraphKind.FULL:
                return self.full_dependency_graph()
            case DependencyGraphKind.COMPRESSED:
                return self.compressed_dependency_graph()
            case DependencyGraphKind.INTERNAL:
                return self.internal_dependency_graph()
            case DependencyGraphKind.COMPRESSED_INTERNAL:
                return self.compressed_internal_dependency_grpah()
