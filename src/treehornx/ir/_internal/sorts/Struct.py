from dataclasses import dataclass
from typing import override

from frozendict import frozendict
from ir.expressions import Var

from . import Pointer, Sort


@dataclass(frozen=True, init=False)
class Struct(Sort):
    """A sort representing a struct type with named fields.

    Attributes:
        name: The name of the struct.
        fields: Dictionary mapping field names to their sorts.
    """

    fields: frozendict[str, Var]

    def __init__(self, name: str, fields: set[Var], struct_ptrs: set[str] = set()):
        super().__init__(name=name)

        fields.update(map(lambda name: Var(name, Pointer(self)), struct_ptrs))

        field_names = {field.name for field in fields}
        if len(field_names) != len(fields):
            raise ValueError("Struct fields must have unique names.")

        object.__setattr__(self, "fields", frozendict({field.name: field for field in fields}))

    @override
    def is_struct(self) -> bool:
        return True
