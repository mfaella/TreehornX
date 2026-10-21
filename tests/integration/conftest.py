import pytest
from pychc.environment import reset_env


@pytest.fixture(autouse=True)
def fresh_smt_environment() -> None:
    """Labels are interned across programs, so the same predicate name can have a different signature in two
    programs: every test declares its predicates in a new pySMT environment."""
    reset_env()
