"""Options changing the size/shape of the CHC systems, not their meaning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class FeatureFlags:
    clean_clause: bool = False
    """Merge the variables equated in a clause body (`chc/clean.py`)."""
    lab_internal_constraints: bool = False
    """Add to every Lab clause the constraints of all the internal steps of its labels, not only of the step to the
    top frame."""
    pre_internal_constraints: bool = False
    """Same as `lab_internal_constraints`, for the clauses of the precondition layer."""
