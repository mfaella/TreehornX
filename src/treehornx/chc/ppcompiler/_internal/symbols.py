from dataclasses import dataclass
from collections import deque

from treehornx.chc.ppcompiler._internal.prepost_nodes import AstNode
from treehornx.chc.ppcompiler.ttype import TType

@dataclass
class Symbol:
    line: int
    column: int
    name: str

@dataclass
class VarSymbol(Symbol):
    type: TType

@dataclass
class MacroSymbol(Symbol):
    param_types: tuple[TType, ...]
    ret_type: TType
    body: AstNode

@dataclass
class EnumTypeSymbol(Symbol):
    pass

type SymbolTable = dict[str, Symbol]
