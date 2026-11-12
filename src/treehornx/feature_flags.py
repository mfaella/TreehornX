"""Options changing the size/shape of the CHC systems, not their meaning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlags:
    clean_clause: bool = False
    """Merge the variables equated in a clause body (`chc/clean.py`)."""
    split: int = 0
    """`--split`: split the final labels before building each system (`SymbolicTree.split`); 0 builds one system,
    1 one per maximal body, 2 one per body, 3 one per root."""
    merge_leaf_constants: bool = False
    """`--merge-leaf-constants` (with `--clean-clause`): in a fact, merge the variables equal to the same constant
    (`chc/clean.py`)."""
    prune_pairs: bool = False
    """`--prune-pairs`: before the tainting, remove the Lab pairs whose data constraints yices2 finds unsatisfiable
    (`chc/Lab/prune.py`)."""
