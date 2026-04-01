from dataclasses import dataclass
from typing import Iterable

from treehornx.chc.ppcompiler.ttype import EnumType, TType


@dataclass(init=False)
class PrePostContext:
    vars: dict[str, TType]
    enums: dict[str, EnumType]
    fields: dict[str, TType]

    def __init__(self, vars: dict[str, TType], fields: dict[str, TType], enums: dict[str, EnumType]):
        self.vars = dict(vars)
        self.enums = dict(enums)
        self.fields = dict(fields)

    def enum(self, name: str) -> EnumType | None:
        return self.enums.get(name, None)

    def var(self, name: str) -> tuple[str, TType] | None:
        if name in self.vars:
            return name, self.vars[name]
        return None

    def field(self, name: str) -> tuple[str, TType] | None:
        if name in self.fields:
            return name, self.fields[name]
        return None
