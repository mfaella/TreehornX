import time
from typing import Callable

from treehornx.ir.function import Function
from treehornx.parser.CParser import CParser


def take_time[T](func: Callable[[], T]) -> tuple[T, float]:
    start = time.time()
    result = func()
    end = time.time()
    return result, end - start
