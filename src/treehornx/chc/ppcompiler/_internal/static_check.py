from dataclasses import dataclass, field
from treehornx.chc.ppcompiler.PrePostContext import PrePostContext
from treehornx.chc.ppcompiler._internal.prepost_nodes import (
    Add, And, Application, AstNode, BinaryOperator, Div, Eq, EnumDecl, EnumIVariant,
    F, Field, FieldState, Ge, Gt, Id, IfThen, IfThenElse, Iff,
    IsLeaf, IsNil, IsRoot, Le, Lt, MacroDecl, Mul, Nat, Neg,
    NodeState, Not, Or, Parent, ParentState, Sub, T, UnaryOperator, Var, VarDecl,
)
from treehornx.chc.ppcompiler._internal.symbols import EnumTypeSymbol, MacroSymbol, SymbolTable, VarSymbol
from treehornx.chc.ppcompiler.ttype import BoolType, EnumType, GenericType, IntType, NodeRef, TType
from treehornx.chc.ppcompiler.messages import (
    ForbiddenNameShadowingError,
    PrePostCompilerError,
    TypeMismatchError, UnknownFieldError,
    UnknownProgramSymbolError, UnknownSymbolError,
)


@dataclass
class TypeSafe:
    pass

@dataclass
class TypeUnsafe:
    errors: list[PrePostCompilerError] = field(default_factory=list)

def type_check(stmts: tuple[AstNode, ...], ctx: PrePostContext) -> TypeSafe | TypeUnsafe:
    ...



def visit(node: AstNode, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> TypeSafe | TypeUnsafe:
    ...

def visit_var_decl(node: VarDecl, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> TypeSafe | TypeUnsafe:
    match ctx.var(node.var_id.text):
        case None:
            error = UnknownProgramSymbolError(node.line, node.column, node.var_id.text)
            return TypeUnsafe(errors=[error])
        case name, _ if (symbol := symbols.get(name)):
            error = ForbiddenNameShadowingError(node.line, node.column, name, symbol.line, symbol.column)
            return TypeUnsafe(errors=[error])
        case name, type:
            symbol = VarSymbol(node.var_id.line, node.var_id.column, name, type)
            symbols[name] = symbol
            return TypeSafe()

def visit_enum_decl(node: EnumDecl, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> TypeSafe | TypeUnsafe:
    match ctx.enum(node.enum_id.text):
        case None:
            error = UnknownProgramSymbolError(node.line, node.column, node.enum_id.text)
            return TypeUnsafe(errors=[error])
        case EnumType(name, _) if (symbol := symbols.get(name)):
            error = ForbiddenNameShadowingError(node.line, node.column, name, symbol.line, symbol.column)
            return TypeUnsafe(errors=[error])
        case EnumType(name, _):
            symbol = EnumTypeSymbol(node.enum_id.line, node.enum_id.column, node.enum_id.text)
            symbols[name] = symbol
            return TypeSafe()

def visit_macro_decl(node: MacroDecl, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> TypeSafe | TypeUnsafe:
    if (symbol := symbols.get(node.macro_id.text)):
        error = ForbiddenNameShadowingError(node.line, node.column, node.macro_id.text, symbol.line, symbol.column)
        return TypeUnsafe(errors=[error])

    errors: list[PrePostCompilerError] = []
    for param in node.params:
        if (param_symbol := symbols.get(param.text)):
            error = ForbiddenNameShadowingError(param.line, param.column, param.text, param_symbol.line, param_symbol.column)
            errors.append(error)
    if errors:
        return TypeUnsafe(errors=errors)

    symbol = MacroSymbol(node.macro_id.line, node.macro_id.column, node.macro_id.text, len(node.params), node.body)

def _assign_type_if_atom(node: AstNode, states: dict[str, TType], symbols: SymbolTable, type: TType) -> TypeSafe | TypeUnsafe:
    match node:
        case Var(name=name):
            symbol = symbols.get(name)
            assert isinstance(symbol, VarSymbol)
            if symbol.type != GenericType() and symbol.type != type:
                error = TypeMismatchError(node.line, node.column, str(type), str(symbol.type))
                return TypeUnsafe(errors=[error])
            if symbol.type == GenericType():
                symbol.type = type
            return TypeSafe()
        case ParentState(state=state) | FieldState(_, state=state) | NodeState(_, state=state):
            if state not in states:
                states[state] = type
                return TypeSafe()
            elif states[state] == GenericType():
                states[state] = type
                return TypeSafe()
            elif states[state] != type:
                error = TypeMismatchError(node.line, node.column, str(type), str(states[state]))
                return TypeUnsafe(errors=[error])
            else:
                return TypeSafe()
        case _:
            return TypeSafe()

def _visit_unary_operator(node: UnaryOperator, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable, intype: TType, outtype: TType) -> tuple[TypeSafe | TypeUnsafe, TType | None]:
    operand = node.operand
    res, type = visit_expression(operand, ctx, states, symbols)
    match res, type:
        case TypeSafe(), GenericType():
            res = _assign_type_if_atom(operand, states, symbols, intype)
            return res, outtype
        case TypeSafe(), other_type if other_type != intype:
            error = TypeMismatchError(operand.line, operand.column, str(intype), str(other_type))
            return TypeUnsafe(errors=[error]), outtype
        case TypeUnsafe(_), _:
            return res, outtype
        case _:
            return TypeSafe(), outtype

def _visit_binary_operator(node: BinaryOperator, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable, intype: TType, outtype: TType) -> tuple[TypeSafe | TypeUnsafe, TType | None]:
    left, right = node.left, node.right
    errors: list[PrePostCompilerError] = []
    lres, ltype = visit_expression(left, ctx, states, symbols)
    match lres, ltype:
        case TypeSafe(), GenericType():
            res = _assign_type_if_atom(left, states, symbols, intype)
            if isinstance(res, TypeUnsafe):
                errors.extend(res.errors)
        case TypeSafe(), other_type if other_type != intype:
            error = TypeMismatchError(left.line, left.column, str(intype), str(other_type))
            errors.append(error)
        case TypeUnsafe(errors=errs), _:
            errors.extend(errs)
        case _:
            pass

    rres, rtype = visit_expression(right, ctx, states, symbols)
    match rres, rtype:
        case TypeSafe(), GenericType():
            res = _assign_type_if_atom(right, states, symbols, intype)
            if isinstance(res, TypeUnsafe):
                errors.extend(res.errors)
        case TypeSafe(), other_type:
            error = TypeMismatchError(right.line, right.column, str(intype), str(other_type))
            errors.append(error)
        case TypeUnsafe(errors=errs), _:
            errors.extend(errs)

    if errors:
        return TypeUnsafe(errors=errors), outtype
    else:
        return TypeSafe(), outtype

def _visit_eq(node: Eq, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> tuple[TypeSafe | TypeUnsafe, TType | None]:
    errors: list[PrePostCompilerError] = []
    left, right = node.left, node.right
    lres, ltype = visit_expression(left, ctx, states, symbols)
    rres, rtype = visit_expression(right, ctx, states, symbols)
    match ltype, rtype:
        case GenericType(), GenericType():
            pass
        case GenericType(), TType():
            res = _assign_type_if_atom(left, states, symbols, rtype)
            if isinstance(res, TypeUnsafe):
                errors.extend(res.errors)
        case TType(), GenericType():
            res = _assign_type_if_atom(right, states, symbols, ltype)
            if isinstance(res, TypeUnsafe):
                errors.extend(res.errors)
        case left_type, right_type if left_type != right_type:
            error = TypeMismatchError(node.line, node.column, str(left_type), str(right_type))
            errors.append(error)
        case _:
            pass
    if isinstance(lres, TypeUnsafe):
        errors.extend(lres.errors)
    if isinstance(rres, TypeUnsafe):
        errors.extend(rres.errors)
    if errors:
        return TypeUnsafe(errors=errors), BoolType()
    else:
        return TypeSafe(), BoolType()

def _visit_if_then(node: IfThen, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> tuple[TypeSafe | TypeUnsafe, TType | None]:
    errors: list[PrePostCompilerError] = []
    cond_res, cond_type = visit_expression(node.condition, ctx, states, symbols)
    if isinstance(cond_res, TypeUnsafe):
        errors.extend(cond_res.errors)
    cond_res = _assign_type_if_atom(node.condition, states, symbols, BoolType())
    if isinstance(cond_res, TypeUnsafe):
        errors.extend(cond_res.errors)
    if cond_type not in {BoolType(), GenericType()}:
        error = TypeMismatchError(node.condition.line, node.condition.column, "bool", str(cond_type))
        errors.append(error)

    then_res, then_type = visit_expression(node.then_, ctx, states, symbols)
    if isinstance(then_res, TypeUnsafe):
        errors.extend(then_res.errors)
    then_res = _assign_type_if_atom(node.then_, states, symbols, BoolType())
    if isinstance(then_res, TypeUnsafe):
        errors.extend(then_res.errors)
    if then_type not in {BoolType(), GenericType()}:
        error = TypeMismatchError(node.then_.line, node.then_.column, "bool", str(then_type))
        errors.append(error)

    if errors:
        return TypeUnsafe(errors=errors), None
    else:
        return TypeSafe(), BoolType()

def _visit_if_then_else(node: IfThenElse, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> tuple[TypeSafe | TypeUnsafe, TType | None]:
    errors: list[PrePostCompilerError] = []
    cond_res, cond_type = visit_expression(node.condition, ctx, states, symbols)
    if isinstance(cond_res, TypeUnsafe):
        errors.extend(cond_res.errors)
    cond_res = _assign_type_if_atom(node.condition, states, symbols, BoolType())
    if isinstance(cond_res, TypeUnsafe):
        errors.extend(cond_res.errors)
    if cond_type not in {BoolType(), GenericType()}:
        error = TypeMismatchError(node.condition.line, node.condition.column, "bool", str(cond_type))
        errors.append(error)

    then_res, then_type = visit_expression(node.then_, ctx, states, symbols)
    if isinstance(then_res, TypeUnsafe):
        errors.extend(then_res.errors)
    if then_type not in {BoolType(), GenericType()}:
        error = TypeMismatchError(node.then_.line, node.then_.column, "bool", str(then_type))
        errors.append(error)

    else_res, else_type = visit_expression(node.else_, ctx, states, symbols)
    if isinstance(else_res, TypeUnsafe):
        errors.extend(else_res.errors)
    if else_type not in {BoolType(), GenericType()}:
        error = TypeMismatchError(node.else_.line, node.else_.column, "bool", str(else_type))
        errors.append(error)

    res_type = GenericType()
    if then_type == GenericType() and else_type != GenericType():


    if errors:
        return TypeUnsafe(errors=errors), None
    else:
        return TypeSafe(), BoolType()


def visit_expression(node: AstNode, ctx: PrePostContext, states: dict[str, TType], symbols: SymbolTable) -> tuple[TypeSafe | TypeUnsafe, TType | None]:
    errors: list[PrePostCompilerError] = []
    match node:
        case T() | F():
            return TypeSafe(), BoolType()

        case Nat():
            return TypeSafe(), IntType()

        case Parent():
            return TypeSafe(), NodeRef()

        case Field(name=name):
            if (field := ctx.field(name)) is None:
                error = UnknownFieldError(node.line, node.column, name)
                return TypeUnsafe(errors=[error]), None
            else:
                return TypeSafe(), field[1]

        case ParentState(state=state):
            if state not in states:
                states[state] = GenericType()
                return TypeSafe(), states[state]
            elif states[state] == GenericType():
                return TypeSafe(), states[state]
            else:
                return TypeSafe(), states[state]

        case FieldState(field=field_name, state=state):
            if (field := ctx.field(field_name)) is None:
                error = UnknownFieldError(node.line, node.column, field_name)
                return TypeUnsafe(errors=[error]), None
            elif field[1] != NodeRef():
                error = TypeMismatchError(node.line, node.column, "node ref", str(field[1]))
                return TypeUnsafe(errors=[error]), None
            elif state not in states:
                states[state] = GenericType()
                return TypeSafe(), states[state]
            elif states[state] == GenericType():
                return TypeSafe(), states[state]
            else:
                return TypeSafe(), states[state]

        case NodeState(node=node_name, state=state):
            if node_name not in symbols:
                error = UnknownSymbolError(node.line, node.column, node_name)
                return TypeUnsafe(errors=[error]), None
            elif (symbol := symbols[node_name]):
                error = UnknownSymbolError(node.line, node.column, node_name)
                return TypeUnsafe(errors=[error]), None
            elif state not in states:
                states[state] = GenericType()
            return TypeSafe(), states[state]

        case EnumIVariant(type_name=type_name, variant=variant):
            if (enum := ctx.enum(type_name)) is None:
                error = UnknownProgramSymbolError(node.line, node.column, type_name)
                return TypeUnsafe(errors=[error]), None
            elif variant not in enum.variants:
                error = UnknownProgramSymbolError(node.line, node.column, f"{type_name}::{variant}")
                return TypeUnsafe(errors=[error]), None
            else:
                return TypeSafe(), enum

        case Neg(operand=operand):
            return _visit_unary_operator(node, ctx, states, symbols, IntType(), IntType())

        case Not(operand=operand):
            return _visit_unary_operator(node, ctx, states, symbols, BoolType(), BoolType())

        case IsNil(operand=operand) | IsRoot(operand=operand) | IsLeaf(operand=operand):
            return _visit_unary_operator(node, ctx, states, symbols, NodeRef(), BoolType())

        case Add(left=left, right=right) | Sub(left=left, right=right) | Mul(left=left, right=right) | Div(left=left, right=right):
            return _visit_binary_operator(node, ctx, states, symbols, IntType(), IntType())

        case And(left=left, right=right) | Or(left=left, right=right) | Iff(left=left, right=right):
            return _visit_binary_operator(node, ctx, states, symbols, BoolType(), BoolType())

        case Eq(left=left, right=right):
            return _visit_eq(node, ctx, states, symbols)

        case Gt(left=left, right=right) | Ge(left=left, right=right) | Lt(left=left, right=right) | Le(left=left, right=right):
            return _visit_binary_operator(node, ctx, states, symbols, IntType(), BoolType())

        case IfThen(condition=condition, then_=then_):
            return _visit_if_then(node, ctx, states, symbols)

        case IfThenElse(condition=condition, then_=then_, else_=else_):
            ...

        case Application(name=name_node, args=args):
            ...
