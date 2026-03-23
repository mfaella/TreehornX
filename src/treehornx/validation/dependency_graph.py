from dataclasses import dataclass

import networkx as nx
from treehornx.enum_labels.core.Event import ERR, LOF, OOM, Exit
from treehornx.enum_labels.core.Label import Label
from treehornx.enum_labels.knitter.StepKind import StepKind
from treehornx.enum_labels.LabelDB import LabelDB
from treehornx.enum_labels.PairDB import PairDB


def build_dependency_graph(labels: LabelDB, pairs: PairDB) -> nx.DiGraph:
    graph: nx.DiGraph = nx.DiGraph()
    for pair in pairs:
        leader = pair.leader()
        follower = pair.follower()
        match pair.last_step_kind():
            case StepKind.EXTERNAL if leader.frame.prev and leader.frame.prev[0] == pair.dir():
                graph.add_edge(follower, leader)
                assert leader.origin
                graph.add_edge(leader.origin, leader)
            case StepKind.INTERNAL:
                for ancestor in labels.ancestors(leader):
                    graph.add_edge(ancestor, leader)
            case _:
                pass
    return graph


def validate_label_end_nodes(graph: nx.DiGraph) -> bool:
    exit_events = {Exit(), ERR(), OOM(), LOF()}
    final_nodes = (node for node, outdegree in graph.out_degree() if outdegree == 0)
    for lab in final_nodes:
        if exit_events.isdisjoint(lab.frame.events):
            return False
    return True
