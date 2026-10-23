"""Options changing the size/shape of the CHC systems, not their meaning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlags:
    clean_clause: bool = False
    """Merge the variables equated in a clause body (`chc/clean.py`)."""
