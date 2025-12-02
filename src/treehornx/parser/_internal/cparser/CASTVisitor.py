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

from .errors import *
from .ExprVisitor import ExprVisitor
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
        self.infunction: bool = False
        self.instructdecl: bool = False
        self.scopes: ScopeStack = ScopeStack()
        self.cond_counter: int = 0
        self.function_components: dict[str, tuple[Sort, set[Var], Sequence[Instruction]]] = dict()
        self.functions: list[Function] = []
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

    def parse_struct_field(self, field_node: c_ast.Decl, struct_name: str) -> Var | str:
        line = cast(int, field_node.coord.line)

        assert field_node.name is not None, "Struct field must have a name."
        assert field_node.init is None, "Struct field declarations with initializers are not supported."

        field_name = cast(str, field_node.name)

        match field_node.type:
            case c_ast.PtrDecl():
                pointee = field_node.type.type.type
                if not isinstance(pointee, c_ast.Struct):
                    raise UnsupportedFeatureError(line, f"Pointer to non-struct type '{pointee}' is not supported.")
                elif pointee.name != struct_name:
                    raise UnsupportedFeatureError(
                        line,
                        f"Pointer to struct type '{pointee.name}' is not supported in struct '{struct_name}'.",
                    )
                return field_name  # Indicate this is a pointer to the same struct

            case c_ast.TypeDecl():
                if not isinstance(field_node.type.type, (c_ast.IdentifierType, c_ast.Enum)):
                    raise UnsupportedFeatureError(
                        line,
                        f"Struct field of type '{type(field_node.type.type).__name__}' is not supported.",
                    )
                sort = self.visit(field_node.type)
                return Var(field_name, sort)

            case _:
                assert False, "Unreachable code reached in parse_struct_field."

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
        line = cast(int, struct_node.coord.line)
        if struct_node.name is None:
            raise UnsupportedFeatureError(line, "Anonymous structs are not supported.")

        if self.infunction:
            if self.decls is not None:
                raise UnsupportedFeatureError(line, "Inline struct definitions inside functions are not supported.")

            struct_name = struct_node.name
            if struct_name not in self.sorts:
                raise UnknownTypeError(line, f"Unknown struct type '{struct_name}'.")
            if not self.sorts[struct_name].is_struct():
                raise UnsupportedFeatureError(line, f"Type '{struct_name}' is not a struct type.")

            return self.sorts[struct_name]

        else:
            self.instructdecl = True
            if struct_node.name in self.sorts:
                raise DuplicateDefinitionError(
                    struct_node.coord.line, f"Struct '{struct_node.name}' is already defined in the current scope."
                )

            if struct_node.decls is None:
                raise UnsupportedFeatureError(struct_node.coord.line, "Structs with no fields are not supported.")

            struct_vars: dict[str, Var] = {}
            struct_ptrs: set[str] = set()
            struct_name: str = struct_node.name

            for field_node in struct_node.decls:
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
                    struct_node.coord.line, f"Struct '{struct_name}' must have at least one pointer field to itself."
                )
            struct = Struct(struct_name, struct_ptrs=struct_ptrs, struct_vars=struct_vars.values())
            self.sorts[struct.name] = struct
            self.instructdecl = False
            return struct

    def visit_Enum(self, node: c_ast.Enum) -> Enum:
        line = cast(int, node.coord.line)
        if node.name is None:
            raise UnsupportedFeatureError(line, "Anonymous enums are not supported.")

        if self.infunction or self.instructdecl:
            if node.values is not None:
                raise UnsupportedFeatureError(line, "Inline enum definitions inside functions are not supported.")
            enum_name = node.name
            if enum_name not in self.sorts:
                raise UnknownTypeError(line, f"Unknown enum type '{enum_name}'.")
            if not self.sorts[enum_name].is_enum():
                raise UnsupportedFeatureError(line, f"Type '{enum_name}' is not an enum type.")
            return self.sorts[enum_name]

        else:
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
                        enumerator.coord.line,
                        f"Enum value '{enumerator_name}' is already defined in enum '{enum_name}'.",
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
            return enum_sort

    def visit_Decl(self, node: c_ast.Decl) -> Iterable[Instruction] | None:
        line = cast(int, node.coord.line)

        if isinstance(node.type, c_ast.FuncDecl):
            if self.infunction:
                return self.visit(node.type)
            else:
                raise UnsupportedFeatureError(
                    line, "Function declarations are only supported inside function definitions."
                )

        elif node.init is not None:
            raise UnsupportedFeatureError(line, "Variable declarations with initializers are not supported.")

        elif not self.infunction:
            if isinstance(node.type, c_ast.TypeDecl):
                raise UnsupportedFeatureError(line, "Global variable declarations are not supported.")
            self.visit(node.type)
        else:
            var_name = cast(str, node.name)
            var_sort = self.visit(node.type)
            self.scopes.declare_variable(var_name, var_sort)
            return []  # empty iterator for variable assignements

    def visit_ParamList(self, node: c_ast.ParamList):
        for param in node.params:
            self.visit(param)

    def visit_FuncDecl(self, node: c_ast.FuncDecl) -> tuple[Sort, str]:
        if not self.infunction:
            raise UnsupportedFeatureError(node.coord.line, "Function declarations are not supported.")
        return_sort = self.visit(node.type)
        name = node.type.declname
        if node.args:
            self.visit(node.args)
        return return_sort, name

    def visit_FuncDef(self, node: c_ast.FuncDef):
        line = cast(int, node.coord.line)
        self.scopes.clear()
        self.scopes.push_scope()
        self.infunction = True

        return_sort, func_name = self.visit(node.decl)
        self.return_sort = return_sort

        instructions = tuple(self.visit(node.body))

        self.scopes.pop_scope()
        self.infunction = False

        try:
            function = Function(func_name, self.scopes.vars, return_sort, instructions)
            self.functions.append(function)
        except IncompatibleReturnTypeError as e:
            raise UnsupportedFeatureError(
                line,
                f"Return type of function '{func_name}' is incompatible with its return statements.",
            )

    def visit_Compound(self, node: c_ast.Compound) -> Iterable[Instruction]:
        for stmt in node.block_items or []:
            yield from self.visit(stmt)

    def visit_expr(self, node: c_ast.Node) -> Expr:
        expr_visitor = ExprVisitor(self.scopes)
        return expr_visitor.visit(node)

    def visit_Assignment(self, node: c_ast.Assignment) -> Iterable[Instruction]:
        if not self.scopes.is_variable_declared(node.lvalue.name):
            raise UndefinedSymbolError(node.coord.line, f"Variable '{node.lvalue.name}' is not defined.")

        match node.lvalue:
            case c_ast.ID():
                lvalue_name = node.lvalue.name
                lvalue = self.scopes.get_variable(lvalue_name)
            case c_ast.StructRef():
                lvalue = self.visit(node.lvalue)
            case _:
                raise UnsupportedFeatureError(node.coord.line, "Only simple variable assignments are supported.")

        rvalue = self.visit_expr(node.rvalue)

        match node.op:
            case "=":
                if sort_of(lvalue) is not sort_of(rvalue):
                    raise UnsupportedFeatureError(
                        node.coord.line,
                        "Type mismatch between left-hand side and right-hand side of assignment.",
                    )
                if sort_of(lvalue).is_ptr():
                    match lvalue, rvalue:
                        case Var(), 0:
                            yield PtrAssignNil(pointer=lvalue)
                        case Var(), Var():
                            yield PtrAssignPtr(left=lvalue, right=rvalue)
                        case Var(), Field():
                            yield PtrAssignField(left=lvalue, right=rvalue)
                        case Field(), 0:
                            yield FieldAssignNil(field=lvalue)
                        case Field(), Var():
                            yield FieldAssignPtr(field=lvalue, pointer=rvalue)
                        case _:
                            raise UnsupportedFeatureError(
                                node.coord.line,
                                "Unsupported assignment operation for pointer types.",
                            )
                else:
                    match lvalue, rvalue:
                        case Var(), _:
                            yield VarAssignExpr(left=lvalue, right=rvalue)
                        case Field(), _:
                            yield FieldAssignExpr(left=lvalue, right=rvalue)
            case _:
                raise UnsupportedFeatureError(
                    node.coord.line,
                    f"Unsupported assignment operator '{node.op}'.",
                )

    def visit_condition(self, node: c_ast.Node) -> Expr:
        cond = self.visit_expr(node)

        match cond:
            case Var(_, Pointer()):
                return Not(PtrIsNil(cond))
            case Var(_, Bool()):
                return Eq(cond, TRUE)
            case _:
                raise UnsupportedFeatureError(
                    node.coord.line,
                    "Only boolean expressions and pointers are supported in conditions.",
                )

    def visit_If(self, node: c_ast.If) -> Iterable[Instruction]:
        cond = self.visit_condition(node.cond)
        iftrue_first, *iftrue_tail = list(self.visit(node.iftrue))
        iffalse_instructions = list(self.visit(node.iffalse)) if node.iffalse else []

        iftrue_label = iftrue_first.name if isinstance(iftrue_first, c_ast.Label) else f"#IFTRUE_{self.cond_counter}"
        endif_label = f"#ENDIF_{self.cond_counter}"

        self.cond_counter += 1

        yield IfGoto(condition=cond, target=iftrue_label)
        yield from iffalse_instructions
        yield Goto(target=endif_label)
        yield iftrue_first.with_label(iftrue_label)
        yield from iftrue_tail
        yield Skip(label=endif_label)

    def visit_While(self, node: c_ast.While) -> Iterable[Instruction]:
        cond = self.visit_condition(node.cond)

        whilebody_first, *whilebody_tail = self.visit(node.stmt)
        whilebody_label = (
            iftrue_first.name if isinstance(iftrue_first, c_ast.Label) else f"#WHILE_BODY_{self.cond_counter}"
        )
        whilecond_label = f"#WHILE_COND_{self.cond_counter}"

        self.cond_counter += 1

        yield Goto(target=whilecond_label)
        yield whilebody_first.with_label(whilebody_label)
        yield from whilebody_tail
        yield IfGoto(condition=cond, target=whilebody_label, label=whilecond_label)

    def visit_Return(self, node: c_ast.Return) -> Iterable[Instruction]:
        ret_expr = None if node.expr is None else self.visit_expr(node.expr)
        ret_sort = UNIT if ret_expr is None else sort_of(ret_expr)
        if ret_sort is not self.return_sort:
            raise UnsupportedFeatureError(
                node.coord.line,
                f"Return statement type '{ret_sort.name}' does not match expected type '{self.return_sort.name}'.",
            )
        if ret_sort is UNIT:
            yield Return()
        else:
            yield Return(value=ret_expr)
