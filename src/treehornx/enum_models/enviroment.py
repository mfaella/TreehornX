from functools import cached_property

from treehornx.ir import Function


class Env:
    """Parameters of one verification run.

    func: the function under analysis.
    k: the number of child fields of a node. It comes from `func` when it is not set.
    m: the bound on the allocations.
    n: the bound on the frames of a label.
    """

    def __init__(
        self,
        func: Function | None = None,
        k: int | None = None,
        m: int | None = None,
        n: int | None = None,
    ):
        self._func = func
        self._k = k
        self._m = m
        self._n = n

    @cached_property
    def func(self) -> Function:
        if self._func is None:
            raise RuntimeError("func has not been set yet")
        return self._func

    @cached_property
    def k(self) -> int:
        if self._k is None:
            raise RuntimeError("m has not been set yet")
        return self._k

    @cached_property
    def m(self) -> int:
        if self._m is None:
            raise RuntimeError("m has not been set yet")
        return self._m

    @cached_property
    def n(self) -> int:
        if self._n is None:
            raise RuntimeError("n has not been set yet")
        return self._n

    def register_function(self, func: Function) -> None:
        if self._func is not None:
            raise RuntimeError("func can be set only once for each enviroment")
        if self._k is not None and self._k != len(func.node.pointer_fields):
            raise RuntimeError("inconsistency between k and number of pointer fields in the node structure")
        self._func = func

    def register_k(self, k: int) -> None:
        if self._k is not None:
            raise RuntimeError("k can be set only once for each enviroment")
        if self._func is not None and k != len(self.func.node.pointer_fields):
            raise RuntimeError("inconsistency between k and number of pointer fields in the node structure")
        self._k = k

    def register_m(self, m: int) -> None:
        if self._m is not None:
            raise RuntimeError("m can be set only once for each enviroment")
        self._m = m

    def register_n(self, n: int) -> None:
        if self._n is not None:
            raise RuntimeError("n can be set only once for each enviroment")
        self._n = n


_DEFAULT_ENV = Env()


def global_env() -> Env:
    return _DEFAULT_ENV
