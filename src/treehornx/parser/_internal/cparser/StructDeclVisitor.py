from typing import cast, override

from ir.expressions import Var
from ir.sorts import *
from ir.sorts import Pointer, Sort, Struct
from pycparser import c_ast

from .errors import DuplicateDefinitionError, UndefinedSymbolError, UnknownTypeError, UnsupportedFeatureError


class StructDeclVisitor(c_ast.NodeVisitor):
    def __init__(self, sorts: dict[str, Sort]):
        self.sorts: dict[str, Sort] = sorts
        self.name: str | None = None

    def visit_Struct(self, struct_node: c_ast.Struct) -> Struct:
        line = cast(int, struct_node.coord.line)
        if struct_node.name is None:
            raise UnsupportedFeatureError(line, "Anonymous structs are not supported.")

        if struct_node.decls is None:
            raise UnsupportedFeatureError(struct_node.coord.line, "Structs with no fields are not supported.")

        struct_vars: dict[str, Var] = {}
        struct_ptrs: set[str] = set()
        struct_name: str = struct_node.name
        self.name = struct_name

        for field_node in struct_node.decls:
            field = self.visit(field_node)
            match field:
                case Var(name, _):
                    if name in struct_vars or name in struct_ptrs:
                        raise DuplicateDefinitionError(
                            field_node.coord.line, f"Field '{name}' is already defined in struct '{struct_name}'."
                        )
                    struct_vars[name] = field
                case str(name):
                    if name in struct_vars or name in struct_ptrs:
                        raise DuplicateDefinitionError(
                            field_node.coord.line, f"Field '{name}' is already defined in struct '{struct_name}'."
                        )
                    struct_ptrs.add(name)

        if not struct_ptrs:
            raise UnsupportedFeatureError(
                struct_node.coord.line, f"Struct '{struct_name}' must have at least one pointer field to itself."
            )
        struct = Struct(struct_name, struct_ptrs=struct_ptrs, struct_vars=struct_vars.values())
        return struct

    def visit_PtrDecl(self, node: c_ast.PtrDecl):
        line = cast(int, node.coord.line)
        pointee = node.type.type
        if not isinstance(pointee, c_ast.Struct):
            raise UnsupportedFeatureError(line, f"Pointer to non-struct type '{pointee}' is not supported.")
        elif pointee.name != self.name:
            raise UnsupportedFeatureError(
                line,
                f"Pointer to struct type '{pointee.name}' is not supported in struct '{self.name}'.",
            )

    def visit_Enum(self, node: c_ast.Enum) -> Enum:
        line = cast(int, node.coord.line)
        if node.name is None:
            raise UnsupportedFeatureError(line, "Anonymous enums are not supported.")
        if node.values is not None:
            raise UnsupportedFeatureError(line, "Inline enum definitions inside functions are not supported.")
        enum_name = node.name
        if enum_name not in self.sorts:
            raise UnknownTypeError(line, f"Unknown enum type '{enum_name}'.")
        if not self.sorts[enum_name].is_enum():
            raise UnsupportedFeatureError(line, f"Type '{enum_name}' is not an enum type.")
        return self.sorts[enum_name]

    def visit_IdentifierType(self, node: c_ast.IdentifierType) -> Sort:
        line = cast(int, node.coord.line)
        type_name = " ".join(node.names)
        if type_name not in self.sorts:
            raise UnknownTypeError(line, f"Unknown type '{type_name}'.")
        return self.sorts[type_name]

    def visit_TypeDecl(self, node: c_ast.Decl) -> Var:
        line = cast(int, node.coord.line)
        if not isinstance(node.type, (c_ast.IdentifierType, c_ast.Enum)):
            raise UnsupportedFeatureError(
                line,
                f"Struct field of type '{type(node.type).__name__}' is not supported.",
            )
        sort = self.visit(node.type)
        return sort

    @override
    def visit_Decl(self, node):
        sort = self.visit(node.type)
        name = node.name
        return Var(name, sort) if sort else name  # if sort is None means name is a pointer to the same struct
