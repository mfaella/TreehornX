from dataclasses import dataclass, field
from functools import cache, cached_property
from typing import Iterable, override

from frozendict import frozendict
from ir.expressions import Var

from .natives import INT, Int, Pointer
from .Sort import Sort


@dataclass(frozen=True, init=False)
class Struct(Sort):
    """A sort representing a struct type with named fields.

    Attributes:
        name: The name of the struct.
        fields: Dictionary mapping field names to their sorts.
    """

    _struct_ptrs: frozenset[str]
    _struct_vars: frozendict[str, Var]

    def __init__(self, name: str, struct_ptrs: Iterable[str], struct_vars: Iterable[Var] = ()):
        super().__init__(name=name)

        ptrs_list = list(struct_ptrs)
        vars_list = list(struct_vars)

        if not ptrs_list:
            raise ValueError("Struct must have at least one pointer field to itself.")

        fields_names = {var.name for var in vars_list} | set(ptrs_list)
        if len(fields_names) != len(ptrs_list) + len(vars_list):
            raise ValueError("Struct fields must have unique names.")

        object.__setattr__(self, "_struct_ptrs", frozenset(ptrs_list))
        object.__setattr__(self, "_struct_vars", frozendict({var.name: var for var in vars_list}))

    @override
    def is_struct(self) -> bool:
        return True

    @cached_property
    def fields(self) -> frozendict[str, Var]:
        """Get all fields of the struct as a mapping from field names to Vars.

        Returns:
            A frozendict mapping field names to their corresponding Vars.
        """
        all_fields = {name: Var(name, Pointer(self)) for name in self._struct_ptrs}
        all_fields.update(self._struct_vars)
        return frozendict(all_fields)
