"""SMT symbols of the states of the negated postcondition automaton A¬post (POPL27, Sec. 7).

The predicate S(σ, state, state_ptr) of the paper turns every tainting flag into a state of A¬post; here the states
are data arguments of the predicate of each tainted label, one variable per state component of the automaton:

* `<prefix>post_n_<STATE>`: the state of the node (state[0]), if it is tainted and active (an output node);
* `<prefix>post_s<j>_<STATE>`: the state of its j-th structural child (state[j]), for every child_is_struct j;
* `<prefix>post_t<p>_<i>_<STATE>`: the state carried by the trail of p at the frame i (state_ptr[p, i]), for every
  key of taint_ptr, in key order.
"""

from dataclasses import dataclass

from treehornx.chc.sdta.SDTAContext import SDTAContext
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.Taint import TaintedLabel
from treehornx.enum_models.Taint.helpers import child_is_struct
from treehornx.enum_models.Taint.TaintPtr import Key


@dataclass(frozen=True)
class PostSymbols:
    ctx: SDTAContext
    k: int

    def _smt_type(self, state: str) -> sx.Type:
        return sx.Type.Int if self.ctx.states[state] == "int" else sx.Type.Bool

    def _states(self, name: str, prefix: str) -> dict[str, sx.Var]:
        return {state: sx.Var(f"{prefix}post_{name}_{state}", self._smt_type(state)) for state in self.ctx.states}

    def has_node_state(self, label: TaintedLabel) -> bool:
        return bool(label.taint_node) and label.lab.frame.active

    def slots(self, label: TaintedLabel) -> list[int]:
        """The structural children of an output node."""
        if not self.has_node_state(label):
            return []
        return [j for j in range(self.k) if child_is_struct(label.lab, j, self.k)]

    def keys(self, label: TaintedLabel) -> list[Key]:
        return sorted(label.taint_ptr)

    def node(self, prefix: str) -> dict[str, sx.Var]:
        return self._states("n", prefix)

    def slot(self, j: int, prefix: str) -> dict[str, sx.Var]:
        return self._states(f"s{j}", prefix)

    def trail(self, key: Key, prefix: str) -> dict[str, sx.Var]:
        p, i = key
        return self._states(f"t{p}_{i}", prefix)

    def symbols(self, label: TaintedLabel, prefix: str) -> list[sx.Var]:
        states = [self.node(prefix)] if self.has_node_state(label) else []
        states += [self.slot(j, prefix) for j in self.slots(label)]
        states += [self.trail(key, prefix) for key in self.keys(label)]
        return [var for state in states for var in state.values()]

    def types(self, label: TaintedLabel) -> list[sx.Type]:
        count = int(self.has_node_state(label)) + len(self.slots(label)) + len(self.keys(label))
        return [self._smt_type(state) for _ in range(count) for state in self.ctx.states]


def equal_states(left: dict[str, sx.Var], right: dict[str, sx.Var]) -> list[sx.SExpr]:
    """Component-wise equality of two states of the same automaton."""
    return [sx.OpExpr(sx.Operator.EQ, left[state], right[state]) for state in left]
