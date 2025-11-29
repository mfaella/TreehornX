from dataclasses import dataclass
from functools import cached_property

from .expressions import Var
from .sorts import Pointer, Struct


@dataclass(frozen=True)
class Enviroment:
    """Represents the environment for a function's IR.

    Attributes:
        node_sort: pointer Sort of each node in the backbone of the input tree.
        root: The root pointer variable of the environment.
        parameters: Set of function parameter variables.
        local_vars: Set of local variables used in the function.
    """

    node_sort: Struct
    root: Var
    local_vars: set[Var]

    def __post_init__(self):
        # root sort must be a pointer type
        if self.root.sort is not Pointer(self.node_sort):
            raise ValueError("self.root.sort is not Pointer(self.node_sort)")

        # no name duplication between root and local vars
        if any(self.root.name == var.name for var in self.local_vars):
            raise ValueError("any(self.root.name == var.name for var in self.local_vars)")
        vars_names_list = [self.root.name, *(v.name for v in self.local_vars)]
        vars_names_set = set(vars_names_list)
        if len(vars_names_set) != len(vars_names_list):
            raise ValueError("len(local_vars_names) != len(local_vars_names_list)")

        # all pointer-typed parameters must point to node_sort
        if any(var.sort.is_struct() for var in self.local_vars):
            raise ValueError("any(var.sort.is_struct() for var in self.local_vars)")
        if any(var.sort.is_ptr() and var.sort.pointee is not self.node_sort for var in self.local_vars):  # type: ignore
            raise ValueError(
                "any(var.sort.is_ptr() and var.sort.sort is not self.node_sort for var in self.local_vars)"
            )

    @cached_property
    def vars(self) -> set[Var]:
        return self.local_vars | {self.root}
