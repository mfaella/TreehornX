"""Initial DFS labels and pairs (first_frame^P)."""

from typing import Iterable

from treehornx import ir
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Dfs.Event import NOP, TFWD
from treehornx.enum_models.Dfs.Flag import Bot, Topp
from treehornx.enum_models.Dfs.Frame import DfsFrame
from treehornx.enum_models.Dfs.helpers import Dfs, Lab, clean_end
from treehornx.enum_models.Dfs.Inst import FindP, NoInst
from treehornx.enum_models.Lab.Frame import Frame


def first_label(function: ir.Function, sigma: Lab) -> Dfs:
    """first_frame^P: the DFS lace starts on the node where the Lab lace ended at `exit`, looking for the
    final value of the root variable p̂. The empty output tree (p̂ nil) is not visited."""
    k, root = function.node.k, function.ROOT
    bots = (Bot(),) * k
    if clean_end(function, sigma) and not sigma.frame.isnil[root]:
        frame = DfsFrame(Bot(), bots, TFWD(len(sigma)), FindP(root), Topp(), sigma)
        return Label(frame, prev=(Internal(), 1))
    return Label(DfsFrame(Bot(), bots, NOP(), NoInst(), Bot(), sigma))


def dfs_initial(
    function: ir.Function, lab_pairs: Iterable[Pair[Frame]]
) -> tuple[set[Dfs], set[Pair[DfsFrame]]]:
    """Start labels and initial pairs of the DFS lace, one first frame for each complete Lab label."""
    pairs = {Pair(first_label(function, p.parent), first_label(function, p.child), p.j) for p in lab_pairs}
    labels = {lab for p in pairs for lab in (p.parent, p.child)}
    starts = {lab for lab in labels if lab.prev is not None}
    return starts, pairs
