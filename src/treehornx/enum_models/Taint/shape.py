"""Tree-shape violations of the output heap, read from the taints (POPL27, Sec. 6.2, the queries C_tree of Fig. 9).

A tainted node has incoming witnesses: the structural edge from a tainted parent whose field was never
overwritten, the trails of the final ⟨pf := p⟩ events of tainted nodes ending on it, and the trail of p̂ for the
output root (its virtual witness). The output is a tree iff no node has two witnesses, no witness reaches a
deallocated node and no node points to itself.

The paper's TQ2 detects two trails of the same pointer merging by walking the lace frame by frame through the
seed of one of them. Here a trail jumps from one link to the next (`TaintingEngine.jumps_up`/`jumps_down`), so it
can only merge where it lands:

* two entries of p in a label leaving it through the same frame σ^{last_upd}: one trail never leaves a label
  twice through the same frame, since every jump goes strictly back in the lace;
* a jump landing on the seed of a field update of p in the neighbour label;
* the trail of p̂ (Rule 1) starting on the seed of a field update of p̂ at the last frame of the lace.

Every merge is an error: both trails come from seeds of tainted nodes or from p̂, so the target has two witnesses.
"""

from collections import Counter
from enum import Enum

from treehornx.enum_models.core.Pair import Pair
from treehornx.enum_models.Lab.helpers import last_upd, points_here
from treehornx.enum_models.Taint.helpers import field_trails
from treehornx.enum_models.Taint.TaintedLabel import TaintedLabel
from treehornx.enum_models.Taint.TaintingEngine import TaintingEngine
from treehornx.enum_models.Taint.TaintPtr import Key


class ShapeError(Enum):
    TWO_POINTER_WITNESSES = "TQ1: two trails end on the same node"
    DANGLING_POINTER_CHILD = "TQ1: a trail ends on a deallocated node"
    TRAILS_MERGE = "TQ2: two trails of the same pointer leave a label through the same frame"
    TRAIL_ON_SEED = "TQ2: a trail lands on the seed of another trail of the same pointer"
    ROOT_SEED_ON_FIELD_SEED = "TQ2: the output root is the target of a final field update"
    STRUCTURAL_AND_POINTER = "TQ3: a structural child is also the end of a trail"
    DANGLING_STRUCTURAL_CHILD = "TQ3: a structural child of a tainted node has been deallocated"
    SELF_LOOP = "TQ4: a tainted node points to itself"


def pointer_witnesses(label: TaintedLabel) -> list[Key]:
    """The trails ending on the node of label (Rule 5)."""
    return [(p, i) for p, i in label.taint_ptr if points_here(label.lab, i, p)]


def seeds(engine: TaintingEngine, label: TaintedLabel) -> set[Key]:
    """The trails started by the final field updates of a tainted node (Rule 3)."""
    return set(field_trails(label.lab, engine.k)) if label.taint_node else set()


def label_errors(engine: TaintingEngine, label: TaintedLabel) -> list[ShapeError]:
    sigma = label.lab
    errors: list[ShapeError] = []
    witnesses = pointer_witnesses(label)
    if sigma.frame.active and len(witnesses) > 1:
        errors.append(ShapeError.TWO_POINTER_WITNESSES)
    if not sigma.frame.active and witnesses:
        errors.append(ShapeError.DANGLING_POINTER_CHILD)
    exits = Counter((p, last_upd(sigma, i, p)) for p, i in label.taint_ptr if (p, i) not in witnesses)
    if any(count > 1 for count in exits.values()):
        errors.append(ShapeError.TRAILS_MERGE)
    label_seeds = seeds(engine, label)
    root_seed = (engine.root, len(sigma))
    if engine.initial(sigma).taint_ptr[root_seed] and root_seed in label_seeds:
        errors.append(ShapeError.ROOT_SEED_ON_FIELD_SEED)
    if any(points_here(sigma, i, p) for p, i in label_seeds):
        errors.append(ShapeError.SELF_LOOP)
    return errors


def pair_errors(engine: TaintingEngine, pair: Pair[TaintedLabel]) -> list[ShapeError]:
    parent, child, j = pair.parent, pair.child, pair.j
    errors: list[ShapeError] = []
    parent_seeds, child_seeds = seeds(engine, parent), seeds(engine, child)
    if any(key in parent_seeds for key, _ in engine.jumps_up(pair)) or any(
        key in child_seeds for key, _ in engine.jumps_down(pair)
    ):
        errors.append(ShapeError.TRAIL_ON_SEED)
    # child_is_struct(σ, j): the field still holds the input child, which exists
    if parent.taint_node and engine.is_structural_child(pair) and parent.lab[1].active_child[j]:
        if not child.lab.frame.active:
            errors.append(ShapeError.DANGLING_STRUCTURAL_CHILD)
        elif pointer_witnesses(child):
            errors.append(ShapeError.STRUCTURAL_AND_POINTER)
    return errors
