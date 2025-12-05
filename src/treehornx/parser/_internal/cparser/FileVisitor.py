import re
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Iterable, Sequence, TextIO, cast

from ir.errors import IncompatibleReturnTypeError
from ir.expressions import TRUE, EnumConst, Eq, Expr, Field, Not, PtrIsNil, Var, sort_of
from ir.function import Function
from ir.instructions import (
    FieldAssignExpr,
    FieldAssignNil,
    FieldAssignPtr,
    Goto,
    IfGoto,
    Instruction,
    PtrAssignField,
    PtrAssignNil,
    PtrAssignPtr,
    Return,
    Skip,
    VarAssignExpr,
)
from ir.sorts import BOOL, INT, REAL, UNIT, Enum, Pointer, Sort, Struct
from parser.Parser import Parser
from pycparser import CParser, c_ast

from .EnumDeclVisitor import EnumDeclVisitor
from .errors import *
from .ExprVisitor import ExprVisitor
from .FuncDefVisitor import FuncDefVisitor
from .ScopeStack import ScopeStack
from .StructDeclVisitor import StructDeclVisitor


def preprocess(code: str) -> str:
    # remove preprocessor directives (e.g. #define, #include, #if/endif, etc.)
    # including any continuation lines that end with a backslash
    preprocessed_code = re.sub(r"(?m)^[ \t]*#(?:.*(?:\\\n.*)*)\n?", "", code)
    return preprocessed_code


parser = CParser()


class FileVisitor(c_ast.NodeVisitor):
    def __init__(self):
        self.sorts: dict[str, Sort] = {
            "int": INT,
            "bool": BOOL,
            "float": REAL,
            "double": REAL,
            "void": UNIT,
            "_Bool": BOOL,
        }
        self.infunction: bool = False
        self.instructdecl: bool = False
        self.scopes: ScopeStack = ScopeStack()
        self.cond_counter: int = 0
        self.functions: dict[str, Function] = {}
        self.return_sort: Sort | None

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

    def visit_FileAST(self, node: c_ast.FileAST):
        for ext in node.ext:
            if not isinstance(ext, (c_ast.Decl, c_ast.FuncDef)):
                raise UnsupportedFeatureError(
                    ext.coord.line, f"Top-level construct '{type(ext).__name__}' is not supported."
                )
            self.visit(ext)

    def visit_TypeDecl(self, node: c_ast.TypeDecl) -> Sort:
        match node.type:
            case c_ast.Struct() | c_ast.Enum() | c_ast.IdentifierType():
                return self.visit(node.type)
            case _:
                assert False, "Unreachable code reached in visit_TypeDecl."

    def visit_IdentifierType(self, node: c_ast.IdentifierType) -> Sort:
        line = cast(int, node.coord.line)
        type_name = " ".join(node.names)
        if type_name not in self.sorts:
            raise UnknownTypeError(line, f"Unknown type '{type_name}'.")
        return self.sorts[type_name]

    def visit_PtrDecl(self, node: c_ast.PtrDecl) -> Pointer:
        line = cast(int, node.coord.line)
        pointee_sort = self.visit(node.type)
        return Pointer(pointee_sort)

    def visit_Struct(self, struct_node: c_ast.Struct) -> Struct:
        struct_decl_visitor = StructDeclVisitor(self.sorts)
        struct = struct_decl_visitor.visit(struct_node)
        if struct.name in self.sorts:
            raise DuplicateDefinitionError(struct_node.coord.line, f"Struct type '{struct.name}' is already defined.")
        self.sorts[struct.name] = struct

    def visit_Enum(self, node: c_ast.Enum) -> Enum:
        enum_decl_visitor = EnumDeclVisitor()
        enum_sort = enum_decl_visitor.visit(node)
        if enum_sort.name in self.sorts:
            raise DuplicateDefinitionError(node.coord.line, f"Enum type '{enum_sort.name}' is already defined.")
        self.sorts[enum_sort.name] = enum_sort
        return enum_sort

    def visit_Decl(self, node: c_ast.Decl) -> Iterable[Instruction] | None:
        line = cast(int, node.coord.line)

        if isinstance(node.type, c_ast.FuncDecl):
            raise UnsupportedFeatureError(line, "Function declarations are only supported inside function definitions.")

        elif node.init is not None:
            raise UnsupportedFeatureError(line, "Variable declarations with initializers are not supported.")

        if isinstance(node.type, c_ast.TypeDecl):
            raise UnsupportedFeatureError(line, "Global variable declarations are not supported.")
        return self.visit(node.type)

    def visit_FuncDef(self, node: c_ast.FuncDef):
        func_visitor = FuncDefVisitor(self.sorts)
        function = func_visitor.visit(node)
        if function.name in self.functions:
            raise DuplicateDefinitionError(node.coord.line, f"Function '{function.name}' is already defined.")
        self.functions[function.name] = function
