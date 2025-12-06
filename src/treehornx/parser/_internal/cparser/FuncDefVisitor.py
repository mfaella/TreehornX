from typing import Iterable, cast

from ir.errors import IncompatibleReturnTypeError
from ir.expressions import *
from ir.function import *
from ir.instructions import *
from ir.sorts import *
from pycparser import c_ast

from .errors import UndefinedSymbolError, UnknownTypeError, UnsupportedFeatureError
from .ExprVisitor import ExprVisitor
from .ScopeStack import ScopeStack


class FuncDefVisitor(c_ast.NodeVisitor):
    def __init__(self, known_sorts: dict[str, Sort]):
        self.known_sorts: dict[str, Sort] = known_sorts
        self.scopes: ScopeStack = ScopeStack()
        self.return_sort: None | Sort = None
        self.cond_counter = 0

    def visit_FuncDef(self, node: c_ast.FuncDef) -> Function:
        line = cast(int, node.coord.line)
        self.scopes.push_scope()

        return_sort, func_name = self.visit(node.decl)
        self.return_sort = return_sort

        instructions = list(self.visit(node.body))

        self.scopes.pop_scope()

        try:
            function = Function(func_name, self.scopes.vars, return_sort, tuple(instructions))
            return function
        except IncompatibleReturnTypeError:
            raise UnsupportedFeatureError(
                line,
                f"Return type of function '{func_name}' is incompatible with its return statements.",
            )

    def visit_FuncDecl(self, node: c_ast.FuncDecl) -> tuple[Sort, str]:
        return_sort = self.visit(node.type)
        name = node.type.declname
        if node.args:
            self.visit(node.args)
        return return_sort, name

    def visit_ParamList(self, node: c_ast.ParamList):
        for param in node.params:
            self.visit(param)

    def visit_Decl(self, node: c_ast.Decl) -> Iterable[Instruction] | None:
        line = cast(int, node.coord.line)

        if isinstance(node.type, c_ast.FuncDecl):
            return self.visit(node.type)

        elif node.init is not None:
            raise UnsupportedFeatureError(line, "Variable declarations with initializers are not supported.")
        var_name = cast(str, node.name)
        var_sort = self.visit(node.type)
        self.scopes.declare_variable(var_name, var_sort)
        return []  # empty iterator for variable assignements

    def visit_TypeDecl(self, node: c_ast.TypeDecl) -> Sort:
        match node.type:
            case c_ast.Struct() | c_ast.Enum() | c_ast.IdentifierType():
                return self.visit(node.type)
            case _:
                assert False, "Unreachable code reached in visit_TypeDecl."

    def visit_IdentifierType(self, node: c_ast.IdentifierType) -> Sort:
        line = cast(int, node.coord.line)
        type_name = " ".join(node.names)
        if type_name not in self.known_sorts:
            raise UnknownTypeError(line, f"Unknown type '{type_name}'.")
        return self.known_sorts[type_name]

    def visit_Struct(self, node: c_ast.Struct) -> Sort:
        line = cast(int, node.coord.line)
        if node.name is None:
            raise UnsupportedFeatureError(line, "Anonymous structs are not supported.")

        if node.decls is not None:
            raise UnsupportedFeatureError(line, "Inline struct definitions inside functions are not supported.")

        struct_name = node.name
        if struct_name not in self.known_sorts:
            raise UnknownTypeError(line, f"Unknown struct type '{struct_name}'.")
        if not self.known_sorts[struct_name].is_struct():
            raise UnsupportedFeatureError(line, f"Type '{struct_name}' is not a struct type.")

        return self.known_sorts[struct_name]

    def visit_Enum(self, node: c_ast.Enum) -> Sort:
        line = cast(int, node.coord.line)
        if node.name is None:
            raise UnsupportedFeatureError(line, "Anonymous enums are not supported.")

        if node.values is not None:
            raise UnsupportedFeatureError(line, "Inline enum definitions inside functions are not supported.")
        enum_name = node.name
        if enum_name not in self.known_sorts:
            raise UnknownTypeError(line, f"Unknown enum type '{enum_name}'.")
        if not self.known_sorts[enum_name].is_enum():
            raise UnsupportedFeatureError(line, f"Type '{enum_name}' is not an enum type.")
        return self.known_sorts[enum_name]

    def visit_PtrDecl(self, node: c_ast.PtrDecl) -> Pointer:
        line = cast(int, node.coord.line)
        pointee_sort = self.visit(node.type)
        if not pointee_sort.is_struct():
            raise UnsupportedFeatureError(line, f"Pointer to non-struct type '{pointee_sort}' is not supported.")
        return Pointer(pointee_sort)

    def visit_Compound(self, node: c_ast.Compound) -> Iterable[Instruction]:
        for stmt in node.block_items or []:
            yield from self.visit(stmt)

    def visit_expr(self, node: c_ast.Node) -> Expr:
        expr_visitor = ExprVisitor(self.scopes)
        return expr_visitor.visit(node)

    def visit_Assignment(self, node: c_ast.Assignment) -> Iterable[Instruction]:
        expr_visitor = ExprVisitor(self.scopes)

        match node.lvalue:
            case c_ast.ID() | c_ast.StructRef():
                lvalue = expr_visitor.visit(node.lvalue)
            case _:
                raise UnsupportedFeatureError(node.coord.line, "Only simple variable assignments are supported.")

        if isinstance(node.rvalue, c_ast.FuncCall):
            if node.rvalue.name.name != "malloc":
                raise UnsupportedFeatureError(
                    node.coord.line,
                    "Only 'malloc' function calls are supported on the right-hand side of assignments.",
                )
            sort = self.visit(node.rvalue)
            if Pointer(sort) is not sort_of(lvalue):
                raise UnsupportedFeatureError(
                    node.coord.line,
                    "Type mismatch between left-hand side and right-hand side of assignment.",
                )
            yield New(lvalue)
        else:
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
                if sort_of(cond) is BOOL:
                    return cond
                else:
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
            whilebody_first.name if isinstance(whilebody_first, c_ast.Label) else f"#WHILE_BODY_{self.cond_counter}"
        )
        whilecond_label = f"#WHILE_COND_{self.cond_counter}"

        self.cond_counter += 1

        yield Goto(target=whilecond_label)
        yield whilebody_first.with_label(whilebody_label)
        yield from whilebody_tail
        yield IfGoto(condition=cond, target=whilebody_label, label=whilecond_label)

    def visit_Return(self, node: c_ast.Return) -> Iterable[Instruction]:
        ret_expr = None if node.expr is None else self.visit_expr(node.expr)
        if self.return_sort is BOOL and isinstance(ret_expr, Var) and sort_of(ret_expr).is_ptr():
            ret_expr = Not(PtrIsNil(ret_expr))
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

    def visit_Label(self, node: c_ast.Label) -> Iterable[Instruction]:
        label_name = node.name
        stmt = node.stmt
        if stmt is None:
            yield Skip(label=label_name)
        else:
            inst = next(self.visit(stmt))
            yield inst.with_label(label_name)

    def visit_Goto(self, node: c_ast.Goto) -> Iterable[Instruction]:
        yield Goto(target=node.name)

    def visit_FuncCall(self, node: c_ast.FuncCall) -> Sort | Iterable[Instruction]:
        match node.name.name:
            case "malloc":
                if len(node.args.exprs) != 1:
                    raise UnsupportedFeatureError(node.coord.line, "Function 'malloc' requires exactly one argument.")
                arg = node.args.exprs[0]
                if not isinstance(arg, c_ast.UnaryOp) and arg.op != "sizeof":
                    raise UnsupportedFeatureError(node.coord.line, "Function 'malloc' requires a 'sizeof' argument.")
                return self.visit(arg)

            case "free":
                if len(node.args.exprs) != 1:
                    raise UnsupportedFeatureError(node.coord.line, "Function 'free' requires exactly one argument.")
                arg = node.args.exprs[0]
                ptr = self.visit_expr(arg)
                if not isinstance(ptr, Var):
                    raise UnsupportedFeatureError(node.coord.line, "Function 'free' requires a variable argument.")
                if not sort_of(ptr).is_ptr():
                    raise UnsupportedFeatureError(node.coord.line, "Function 'free' requires a pointer argument.")
                return (Free(pointer=ptr),)
            case "sizeof":
                if len(node.args.exprs) != 1:
                    raise UnsupportedFeatureError(node.coord.line, "Function 'sizeof' requires exactly one argument.")
                arg = node.args.exprs[0]
                match arg:
                    case c_ast.TypeDecl():
                        sort = self.visit(arg)
                        return sort
                    case _:
                        raise UnsupportedFeatureError(node.coord.line, "Function 'sizeof' requires a type as argument.")

            case _:
                raise UnsupportedFeatureError(node.coord.line, f"Function call to '{node.name.name}' is not supported.")

    def visit_UnaryOp(self, node: c_ast.UnaryOp) -> Sort:
        match node.op:
            case "sizeof":
                return self.visit(node.expr.type)
            case _:
                raise UnsupportedFeatureError(
                    node.coord.line, f"Unary operator '{node.op}' is not accepted as statement."
                )
