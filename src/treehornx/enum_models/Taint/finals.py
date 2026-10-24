"""Final states and pairs of the tainting: the saturated ones that compose a whole tree from a root.

A state is final iff it is saturated and, for every child index j it has pairs for, some saturated pair
(state, child, j) has a final child; a state with no pairs as parent is a leaf. This is a greatest fixpoint
(an input tail never reached by the lace is an infinite chain of the same label), computed by removing the
states that lose the support of all their pairs for some j, in O(|states| + |pairs|). The result keeps only
what hangs under a final root.
"""

from collections import Counter, deque
from typing import Callable, Iterable, Mapping, TypeVar

from treehornx.enum_models.core.Pair import Pair


SN = TypeVar("SN")


def saturated_finals(
    states: Iterable[SN],
    sat_pairs: set[Pair[SN]],
    parent_index: Mapping[SN, set[Pair[SN]]],
    child_index: Mapping[SN, set[Pair[SN]]],
    is_root: Callable[[SN], bool],
) -> tuple[set[SN], set[Pair[SN]]]:
    """`states` and `sat_pairs` are the saturated states and pairs, the indices hold all the pairs (by parent and
    by child): the child indices of a state are those of all its pairs, saturated or not."""
    no_pairs: set[Pair[SN]] = set()
    alive = set(states)

    # greatest fixpoint: support[(s, j)] counts the saturated pairs (s, c, j) with c still alive
    support = Counter((p.parent, p.j) for p in sat_pairs if p.child in alive)
    queue = deque(s for s in alive if any(support[(s, p.j)] == 0 for p in parent_index.get(s, no_pairs)))
    while queue:
        s = queue.popleft()
        if s not in alive:
            continue
        alive.discard(s)
        for p in child_index.get(s, no_pairs):
            if p in sat_pairs and p.parent in alive:
                support[(p.parent, p.j)] -= 1
                if support[(p.parent, p.j)] == 0:
                    queue.append(p.parent)

    # top-down: what hangs under a final root
    roots = [s for s in alive if is_root(s)]
    final_states: set[SN] = set(roots)
    final_pairs: set[Pair[SN]] = set()
    frontier = deque(roots)
    while frontier:
        s = frontier.popleft()
        for p in parent_index.get(s, no_pairs):
            if p in sat_pairs and p.child in alive:
                final_pairs.add(p)
                if p.child not in final_states:
                    final_states.add(p.child)
                    frontier.append(p.child)
    return final_states, final_pairs
