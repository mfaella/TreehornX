from dataclasses import dataclass

@dataclass(frozen=True)
class TType:
    name: str

@dataclass(frozen=True)
class GenericType(TType):
    def __init__(self):
        super().__init__(name="generic")

@dataclass(frozen=True)
class IntType(TType):
    def __init__(self):
        super().__init__(name="Int")

@dataclass(frozen=True)
class BoolType(TType):
    def __init__(self):
        super().__init__(name="Bool")

@dataclass(frozen=True)
class EnumType(TType):
    variants: set[str]

@dataclass(frozen=True)
class NodeRef(TType):
    def __init__(self):
        super().__init__(name="NodeRef")
