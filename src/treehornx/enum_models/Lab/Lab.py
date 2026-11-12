import weakref
from typing import Callable

from treehornx.enum_models.core.Label import Label
from treehornx.enum_models.Lab.Frame import Frame


Lab = Label[Frame]

LabFactory = Callable[[Frame, "Lab | None"], Lab]
"""Builds a label from its top frame and its prefix; the engine builds every label through one."""

_pool: "weakref.WeakValueDictionary[tuple[Frame, Lab | None], Lab]" = weakref.WeakValueDictionary()


def intern_lab(frame: Frame, prefix: Lab | None = None) -> Lab:
    """The label of `frame` on `prefix`, the same instance as long as one is alive."""
    key = (frame, prefix)
    label = _pool.get(key)
    if label is None:
        label = Lab(frame, prefix)
        _pool[key] = label
    return label
