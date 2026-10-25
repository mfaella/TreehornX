"""The tree-shape system over the tainted labels, with the memory errors of the configuration: memory-unsafe
programs stay unsat, and memory-safe ones are sat since their outputs are trees (`test_lab_chc.py` cases)."""

from dataclasses import replace

import pytest

from .config import TestConfig, params, run
from .test_lab_chc import CONFIGS as LAB_CONFIGS


CASES = params(*(replace(config, layer="tree_shape") for config in LAB_CONFIGS))


@pytest.mark.parametrize("config", CASES)
def test_tree_shape_memory_safety(config: TestConfig) -> None:
    assert run(config) == config.expected
