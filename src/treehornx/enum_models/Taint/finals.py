"""Final states and pairs of the tainting: the saturated ones that compose a whole tree from a root.

A state is final iff it is saturated and, if it has pairs as parent, for every child index j in [0, arity) some
saturated pair (state, child, j) has a final child; a state with no pairs as parent is a leaf. The clauses of a
parent collect one child for every index (`BotUpAutomataRunner._has_all_children`), so a parent missing an index
has no clause, and neither has anything that needs it. This is a greatest fixpoint
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
    arity: int,
) -> tuple[set[SN], set[Pair[SN]]]:
    """`states` and `sat_pairs` are the saturated states and pairs, the indices hold all the pairs (by parent and
    by child): a state is a parent when it has pairs as parent, saturated or not, and then it needs a final child
    for every index in [0, `arity`)."""
    no_pairs: set[Pair[SN]] = set()
    alive = set(states)

    # greatest fixpoint: support[(s, j)] counts the saturated pairs (s, c, j) with c still alive
    support = Counter((p.parent, p.j) for p in sat_pairs if p.child in alive)
    queue = deque(s for s in alive if parent_index.get(s) and any(support[(s, j)] == 0 for j in range(arity)))
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
