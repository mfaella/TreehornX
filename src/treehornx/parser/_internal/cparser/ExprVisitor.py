from cmath import isinf
from dataclasses import dataclass, field
from typing import override

from ir.expressions import Add, And, Div, Eq, Expr, Ge, Gt, Le, Lt, Mod, Mul, Ne, Not, Or, PtrIsNil, PtrIsPtr, Sub, Var
from ir.instructions import Instruction
from ir.sorts import BOOL, Int, Real, Sort
from ir.utils import *
from parser._internal.cparser.errors import UndefinedSymbolError, UnsupportedFeatureError
from pycparser import c_ast

from .ScopeStack import ScopeStack


@dataclass
class ExprVisitor(c_ast.NodeVisitor):
    scopes: ScopeStack
    instructions: list[Instruction] = field(default_factory=list, init=False)
    is_sub_expr: bool = field(default=False, init=False)

    def visit_ID(self, node: c_ast.ID) -> Var:
        if not self.scopes.is_variable_declared(node.name):
            raise UndefinedSymbolError(f"Variable '{node.name}' not found in any scope.")

        var = self.scopes.get_variable(node.name)
        return var

    def visit_Constant(self, node: c_ast.Constant) -> Expr:
        match node.type:
            case "int":
                return int(node.value)
            case "float" | "double":
                return float(node.value)
            case _:
                raise UnsupportedFeatureError(node.coord.line, f"Constant of type '{node.type}' is not supported.")

    def visit_StructRef(self, node: c_ast.StructRef) -> Expr:
        if node.type != "->":
            raise UnsupportedFeatureError(node.coord.line, "Direct struct field access is not supported.")

        if self.is_sub_expr:
            raise UnsupportedFeatureError(
                node.coord.line,
                "Struct field access is not supported within sub-expressions.",
            )

        base_expr = self.visit(node.name)
        field_name = node.field.name
        return Field(base=base_expr, field_name=field_name)

    def visit_UnaryOp(self, node: c_ast.UnaryOp) -> Expr:
        self.is_sub_expr = True
        match node.op:
            case "!":
                expr = self.visit(node.expr)
                if isinstance(expr, Var) and sort_of(expr).is_ptr():
                    return PtrIsNil(expr)
                else:
                    return Not(expr)
            case _:
                raise UnsupportedFeatureError(node.coord.line, f"Unary operator '{node.op}' is not supported.")

    def visit_BinaryOp(self, node: c_ast.BinaryOp) -> Expr:
        self.is_sub_expr = True
        left = self.visit(node.left)
        right = self.visit(node.right)

        type_safe_arith_expr = lambda l, r: is_same_sort(l, r) and is_arithmetic_expression(l)
        type_safe_bool_expr = lambda l, r: is_same_sort(l, r) and sort_of(l) is BOOL

        match node.op:
            case "!=" | "==" if not is_same_sort(left, right):
                raise UnsupportedFeatureError(
                    node.coord.line,
                    f"Cannot compare expressions of different sorts: {sort_of(left)} and {sort_of(right)}.",
                )
            case "+" | "-" | "*" | "/" | "%" | "<" | "<=" | ">" | ">=" if not type_safe_arith_expr(left, right):
                raise UnsupportedFeatureError(
                    node.coord.line,
                    f"Operator '{node.op}' requires both operands to be of the same arithmetic sort (Int or Real).",
                )
            case "&&" | "||":
                if isinstance(left, Var) and sort_of(left).is_ptr():
                    left = Not(PtrIsNil(left))
                if isinstance(right, Var) and sort_of(right).is_ptr():
                    right = Not(PtrIsNil(right))
                if not type_safe_bool_expr(left, right):
                    raise UnsupportedFeatureError(
                        node.coord.line,
                        f"Operator '{node.op}' requires both operands to be of the same Boolean sort.",
                    )

        match node.op:
            case "+":
                return Add(left, right)
            case "-":
                return Sub(left, right)
            case "*":
                return Mul(left, right)
            case "/":
                return Div(left, right)
            case "%":
                return Mod(left, right)
            case "<":
                return Lt(left, right)
            case "<=":
                return Le(left, right)
            case ">":
                return Gt(left, right)
            case ">=":
                return Ge(left, right)
            case "&&":
                return And(left, right)
            case "||":
                return Or(left, right)
            case "==":
                if sort_of(left).is_ptr():
                    return PtrIsPtr(left, right)
                else:
                    return Eq(left, right)
            case "!=":
                if sort_of(left).is_ptr():
                    return Not(PtrIsPtr(left, right))
                else:
                    return Ne(left, right)
            case _:
                raise UnsupportedFeatureError(node.coord.line, f"Binary operator '{node.op}' is not supported.")
