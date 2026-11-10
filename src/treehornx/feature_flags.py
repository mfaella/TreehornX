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
