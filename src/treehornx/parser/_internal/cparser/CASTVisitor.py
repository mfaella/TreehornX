import re
import subprocess
from cmath import isinf
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Iterable, TextIO, cast

from ir.enviroment import Enviroment
from ir.expressions import Var
from ir.function import Function
from ir.instructions import Instruction
from ir.sorts import BOOL, INT, REAL, UNIT, Enum, Sort, Struct
from parser.Parser import Parser
from pycparser import CParser, c_ast

from .errors import *
from .ScopeStack import ScopeStack


def preprocess(code: str) -> str:
    # remove preprocessor directives (e.g. #define, #include, #if/endif, etc.)
    # including any continuation lines that end with a backslash
    preprocessed_code = re.sub(r"(?m)^[ \t]*#(?:.*(?:\\\n.*)*)\n?", "", code)
    return preprocessed_code


parser = CParser()


class CASTVisitor(c_ast.NodeVisitor):
    def __init__(self):
        self.sorts: dict[str, Sort] = {
            "int": INT,
            "bool": BOOL,
            "float": REAL,
            "double": REAL,
            "void": UNIT,
            "_Bool": BOOL,
        }

    @classmethod
    def produce_ast_from_src(cls, src: str) -> c_ast.FileAST:
        """
        Parse C code provided as a string and return a pycparser AST.
        """
        preprocessed_code = preprocess(src)
        print(preprocessed_code)
        return parser.parse(preprocessed_code)

    @classmethod
    def produce_ast_from_textio(cls, source: TextIO) -> c_ast.FileAST:
        """
        Parse C code from either:
        - a TextIO object (open file handle, io.StringIO, etc.)
        and return the pycparser AST.
        """

        try:
            source.seek(0)
        except Exception:
            pass  # Not all TextIO types support seek()
        code = source.read()

        return cls.produce_ast_from_src(code)

    def parse_struct_field(self, field_node: c_ast.Decl, struct_name: str) -> Var | str:
        line = cast(int, field_node.coord.line)

        assert field_node.name is not None, "Struct field must have a name."
        assert field_node.init is None, "Struct field declarations with initializers are not supported."

        field_name = cast(str, field_node.name)
        if isinstance(field_node.type, c_ast.PtrDecl):
            pointee = field_node.type.type.type
            if not isinstance(pointee, c_ast.Struct):
                raise UnsupportedFeatureError(line, f"Pointer to non-struct type '{pointee}' is not supported.")
            elif pointee.name != struct_name:
                raise UnsupportedFeatureError(
                    line,
                    f"Pointer to struct type '{pointee.name}' is not supported in struct '{struct_name}'.",
                )
            return field_name  # Indicate this is a pointer to the same struct

        elif isinstance(field_node.type.type, c_ast.IdentifierType):
            id_type_node = field_node.type.type
            type_name = " ".join(id_type_node.names)
            if type_name not in self.sorts:
                raise UnknownTypeError(
                    id_type_node.coord.line, f"Unknown type '{type_name}' for variable '{type_name}'."
                )

            return Var(field_name, self.sorts[type_name])

        elif isinstance(field_node.type.type, c_ast.Enum):
            enum_node = field_node.type.type
            if enum_node.name is None:
                raise UnsupportedFeatureError(line, "Anonymous enum variable declarations are not supported.")
            enum_name = enum_node.name
            assert enum_name in self.sorts, "Enum type must be defined before use."
            enum_sort = self.sorts[enum_name]
            return Var(field_name, enum_sort)

        else:
            raise UnsupportedFeatureError(
                line, f"Struct field of type '{type(field_node.type.type).__name__}' is not supported."
            )

    def visit_FileAST(self, node: c_ast.FileAST):
        for ext in node.ext:
            if not isinstance(ext, (c_ast.Decl, c_ast.FuncDef)):
                raise UnsupportedFeatureError(
                    ext.coord.line, f"Top-level construct '{type(ext).__name__}' is not supported."
                )
            self.visit(ext)

    def visit_Decl(self, node: c_ast.Decl):
        if isinstance(node.type, c_ast.Struct):
            self.visit_Struct(node.type)
        elif isinstance(node.type, c_ast.Enum):
            self.visit_Enum(node.type)
        else:
            raise UnsupportedFeatureError(
                node.coord.line, f"Declaration of type '{type(node.type).__name__}' is not supported."
            )

    def visit_Struct(self, node: c_ast.Struct):
        if node.name is None:
            raise UnsupportedFeatureError(node.coord.line, "Anonymous structs are not supported.")

        if node.name in self.sorts:
            raise DuplicateDefinitionError(
                node.coord.line, f"Struct '{node.name}' is already defined in the current scope."
            )

        if node.decls is None:
            raise UnsupportedFeatureError(node.coord.line, "Structs with no fields are not supported.")

        struct_vars: dict[str, Var] = {}
        struct_ptrs: set[str] = set()
        struct_name: str = node.name

        for field_node in node.decls:
            field = self.parse_struct_field(field_node, struct_name)
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
                node.coord.line, f"Struct '{struct_name}' must have at least one pointer field to itself."
            )
        struct = Struct(struct_name, struct_ptrs=struct_ptrs, struct_vars=struct_vars.values())
        self.sorts[struct.name] = struct

    def visit_Enum(self, node: c_ast.Enum):
        assert node.name is not None, "Anonymous enums are not supported."

        assert node.values is not None, "Enums with no values are not supported."

        enum_name: str = node.name
        if enum_name in self.sorts:
            raise DuplicateDefinitionError(
                node.coord.line, f"Enum '{enum_name}' is already defined in the current scope."
            )
        enum_values: dict[str, int] = dict()

        enumerator_value_counter = 0
        for enumerator in node.values.enumerators:
            enumerator_name = enumerator.name
            enumerator_value = enumerator_value_counter
            if enumerator_name in enum_values:
                raise DuplicateDefinitionError(
                    enumerator.coord.line, f"Enum value '{enumerator_name}' is already defined in enum '{enum_name}'."
                )
            if enumerator.value is not None and (
                not isinstance(enumerator.value, c_ast.Constant) or enumerator.value.type != "int"
            ):
                raise UnsupportedFeatureError(
                    enumerator.coord.line,
                    f"Enum value '{enumerator_name}' must be a positive integer constant in enum '{enum_name}'.",
                )
            if enumerator.value:
                enumerator_value = int(enumerator.value.value)
            enum_values[enumerator_name] = enumerator_value
            enumerator_value_counter = enumerator_value + 1

        enum_sort = Enum(enum_name, enum_values)
        self.sorts[enum_name] = enum_sort


# ArrayDecl,
