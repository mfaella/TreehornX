"""Memory safety under a precondition through the bottom-up run of its automaton.

The system is sat when no input accepted by the precondition leads to a null-pointer dereference. The
"safe" programs below are safe only thanks to the precondition: without it they can dereference nil.
"""

import pytest

from treehornx.chc.solvers import Status
from treehornx.feature_flags import FeatureFlags

from .config import TestConfig, params, run


SAT, UNSAT = Status.SAT, Status.UNSAT

CASES = params(
    TestConfig("sll_sorted_safe_first_lt_last", SAT, pre="sll_sorted_strict"),
    TestConfig("sll_sorted_unsafe_first_lt_last", UNSAT, pre="sll_sorted_strict"),
    TestConfig("bst_safe_min_lt_max", SAT, pre="bst_strict"),
    TestConfig("bst_unsafe_min_lt_max", UNSAT, pre="bst_strict"),
    TestConfig(
        "avl_safe_insert_bal",
        SAT,
        m=1,
        pre="avl",
        solver="eldarica",
        timeout=1200,
        flags=FeatureFlags(clean_clause=True),
        marks=(pytest.mark.slow,),
    ),
    # safe for every input, the precondition must not change the result
    TestConfig("sll_safe_find", SAT, pre="sll_sorted"),
    TestConfig("bst_safe_insert_field_nil", SAT, m=1, pre="bst_strict"),
    TestConfig(
        "rb_safe_insert",
        SAT,
        m=1,
        nil_fields=("parent",),
        pre="rb",
        solver="eldarica",
        timeout=1200,
        flags=FeatureFlags(clean_clause=True),
    ),
)

# safe only thanks to the precondition
WITHOUT_PRECONDITION = params(
    TestConfig("sll_sorted_safe_first_lt_last", UNSAT),
    TestConfig("bst_safe_min_lt_max", UNSAT),
    TestConfig("avl_safe_insert_bal", UNSAT, m=1, flags=FeatureFlags(True)),
)


@pytest.mark.parametrize("config", CASES)
def test_memory_safety_under_precondition(config: TestConfig) -> None:
    assert run(config) == config.expected


@pytest.mark.parametrize("config", WITHOUT_PRECONDITION)
def test_unsafe_without_precondition(config: TestConfig) -> None:
    assert run(config) == config.expected
