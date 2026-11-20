"""Options changing the size/shape of the CHC systems, not their meaning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlags:
    split: int = 0
    """`--split`: split the final labels before building each system (`SymbolicTree.split`); 0 builds one system,
    1 one per maximal body, 2 one per body, 3 one per root."""
    prune_pairs: bool = False
    """`--prune-pairs`: before the tainting, remove the Lab pairs whose data constraints yices2 finds unsatisfiable
    (`chc/Lab/prune.py`)."""
    eq_prop: int = 0
    """`--eq-prop`: the equality must analysis (`analysis/constr/phases.py::eq_phase`); the symbols of a class leave the
    predicate arguments but one. 0 off, 1 bottom-up, 2 bottom-up then top-down."""
    const_prop: int = 0
    """`--const-prop`: the constant propagation (`analysis/constr/phases.py::const_phase`); the symbols equal to a
    constant leave the predicate arguments, the labels without a feasible derivation are removed. 0 off, 1
    bottom-up, 2 bottom-up then top-down."""
