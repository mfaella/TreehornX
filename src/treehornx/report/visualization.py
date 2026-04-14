import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable

import pydot

from treehornx.enum_labels import KnittedTrees, Step
from treehornx.enum_labels.core.Dir import Dir, Down, Internal, Up
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label
from treehornx.ir.function import Function
from treehornx.ir.instructions import Return
from treehornx.report.format import frame_to_json


class DependencyGraphKind(Enum):
    FULL = "full"
    COMPRESSED = "compressed"
    INTERNAL = "internal"


@dataclass(slots=True)
class DependencyGraphInfo:
    kind: DependencyGraphKind
    nodes_count: int


@dataclass
class DependencyGraphBuilder:
    function: Function
    lace_over_approx: KnittedTrees

    def _id(self, label: Label) -> int:
        return self.lace_over_approx.id(label)

    def _is_endless_loop_pivot(self, label: Label) -> bool:
        return self.lace_over_approx.is_endless_loop_pivot(label)

    def _steps(self) -> Iterable[Step]:
        return self.lace_over_approx.steps()

    def _label_name(self, label: Label) -> str:
        lab_id = self._id(label)
        return f"Lab{lab_id}"

    def _ancestors(self, lab: Label) -> Iterable[Label]:
        for step in self._steps():
            if step.dir == Internal() and step.out_label == lab:
                yield step.in_label

    def _create_label_node(self, graph: pydot.Dot, lab: Label):
        lab_name = self._label_name(lab)
        if graph.get_node(lab_name):
            return
        f = lab.frame
        fjson = frame_to_json(f)
        tooltip = json.dumps(fjson, indent=2)

        if self._is_endless_loop_pivot(lab):
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

    def _dir_to_edge_label(self, dir: Dir) -> str:
        match dir:
            case Up():
                return "U"
            case Internal():
                return "I"
            case Down(j):
                return f"D({j})"

    def add_lace_step_dependency(self, step: Step, graph: pydot.Dot):
        in_label = step.in_label
        out_label = step.out_label
        self._create_label_node(graph, in_label)
        self._create_label_node(graph, out_label)
        in_label_name = self._label_name(in_label)
        out_label_name = self._label_name(out_label)
        edge_label = self._dir_to_edge_label(step.dir)
        edge = pydot.Edge(in_label_name, out_label_name, label=edge_label, color="blue")
        graph.add_edge(edge)

    def add_structural_dependency(self, in_label: Label, out_label: Label, graph: pydot.Dot):
        self._create_label_node(graph, in_label)
        self._create_label_node(graph, out_label)
        in_label_name = self._label_name(in_label)
        out_label_name = self._label_name(out_label)
        edge = pydot.Edge(in_label_name, out_label_name, color="grey")
        graph.add_edge(edge)

    def _make_graph(self, graph_name: str) -> pydot.Dot:
        engine = self._engine()
        graph = pydot.Dot(graph_name, type="digraph", style="filled", bgcolor="lightgrey", strict=True, engine=engine)
        return graph

    def full_dependency_graph(self) -> pydot.Dot:
        graph = self._make_graph("full dependency graph")

        for step in self._steps():
            match step.dir:
                case Internal():
                    self.add_lace_step_dependency(step, graph)
                case _:
                    self.add_lace_step_dependency(step, graph)
                    assert step.out_label.origin is not None
                    self.add_structural_dependency(step.out_label.origin, step.out_label, graph)

        return graph

    def compressed_dependency_graph(self) -> pydot.Dot:
        graph = self._make_graph("compressed dependency graph")

        for step in self._steps():
            in_label = step.in_label
            out_label = step.out_label
            match step.dir:
                case Up() | Down(_):
                    self.add_lace_step_dependency(step, graph)
                case Internal() if out_label.frame.events.intersection({Exit(), ERR(), OOM(), LOF()}):
                    if out_label.origin is None:
                        self._create_label_node(graph, out_label)
                    else:
                        compressed_step = replace(step, in_label=out_label.origin)
                        self.add_lace_step_dependency(compressed_step, graph)
                case _:
                    pass

        return graph

    def internal_dependency_graph(self) -> pydot.Dot:
        graph = self._make_graph("internal dependency graph")

        for step in self._steps():
            in_label = step.in_label
            out_label = step.out_label
            if step.dir == Internal():
                self.add_lace_step_dependency(step, graph)
            else:
                assert out_label.origin is not None
                self.add_structural_dependency(out_label.origin, in_label, graph)

        return graph

    def dependency_graph(self, kind: DependencyGraphKind) -> pydot.Dot:
        match kind:
            case DependencyGraphKind.FULL:
                return self.full_dependency_graph()
            case DependencyGraphKind.COMPRESSED:
                return self.compressed_dependency_graph()
            case DependencyGraphKind.INTERNAL:
                return self.internal_dependency_graph()
