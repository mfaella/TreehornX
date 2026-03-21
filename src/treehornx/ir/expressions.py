from __future__ import annotations

import math
import operator
from dataclasses import dataclass, field, is_dataclass
from functools import reduce
from itertools import chain
from typing import (
    Any,
    Callable,
    ClassVar,
    Protocol,
    TypeAlias,
    TypeVar,
    override,
    runtime_checkable,
)

from ._internal.sorts.Enum import BOOL, Enum
from ._internal.sorts.natives import INT, REAL, Pointer
from ._internal.sorts.Sort import Sort


# Variables classes
@dataclass(frozen=True)
class Var:
    """A named variable with an associated Sort.

    Attributes:
        name: The variable identifier.
        sort: The variable's type (a Sort instance).
    """

    name: str
    sort: Sort

    def __post_init__(self):
        if self.sort.is_unit():
            raise ValueError("self.sort.is_unit()")

    @override
    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Field:
    ptr: Var
    name: str
    """A field access expression.

    This represents accessing field `name` from a pointer `ptr` (e.g. `ptr.field`).
    The `ptr` must be a pointer-sorted variable.
    """

    def __post_init__(self):
        if not self.ptr.sort.is_ptr():
            raise ValueError("not self.ptr.is_ptr()")
        if not self.ptr.sort.pointee.is_struct():  # type: ignore
            raise ValueError("not self.ptr.sort.is_struct()")
        if self.name not in self.ptr.sort.pointee.fields:  # type: ignore
            raise ValueError("self.name not in self.ptr.sort.fields")

    @override
    def __str__(self) -> str:
        return f"{self.ptr.name}.{self.name}"


@dataclass(frozen=True)
class EnumConst:
    sort: Enum
    value: str

    _pool: ClassVar[dict[EnumConst, EnumConst]] = {}

    def __new__(cls, sort: Enum, value: str) -> EnumConst:
        """Create or retrieve an interned EnumConst instance.

        Args:
            sort: The sort of the enumeration.
            value: The value of the enumeration.
        """
        instance = object.__new__(cls)
        object.__setattr__(instance, "sort", sort)
        object.__setattr__(instance, "value", value)
        if instance not in cls._pool:
            cls._pool[instance] = instance
        return cls._pool[instance]

    def __post_init__(self):
        if not self.sort.exists(self.value):
            raise ValueError(f"value '{self.value}' not in enum sort {self.sort}")

    def __deepcopy__(self, _):
        # EnumConst instances are immutable and interned, so we can return the same instance
        return self


TRUE = EnumConst(BOOL, "TRUE")
FALSE = EnumConst(BOOL, "FALSE")


@runtime_checkable
class Operator(Protocol):
    """Protocol for expression operators.

    Implementations must provide `args()` returning the operand expressions and
    `name()` returning the operator's textual name used when rendering.
    """

    def args(self) -> tuple[Expr, ...]: ...

    def arg(self, index: int) -> Expr:
        return self.args()[index]

    def name(self) -> str: ...

    @override
    def __str__(self) -> str:
        args: tuple[Expr, ...] = self.args()
        name = self.name()
        return f"({name} {' '.join(map(str, args))})"


@dataclass(frozen=True, slots=True)
class _UnaryOperator(Operator):
    """Base class for operators with a single argument.

    Concrete unary operators inherit this and implement `name()`.
    """

    argument: Expr

    @override
    def args(self):
        return (self.argument,)


@dataclass(frozen=True, slots=True)
class _BinaryOperator(Operator):
    """Base class for operators with two arguments.

    Concrete binary operators inherit this and implement `name()`.
    """

    left: Expr
    right: Expr

    @override
    def args(self):
        return (self.left, self.right)


@dataclass(frozen=True)
class _AssociativeOperator(Operator):
    """Base class for operators that accept a variable number of arguments.

    Examples include logical conjunction/disjunction and n-ary arithmetic.
    """

    arguments: tuple[Expr, ...] = field(init=False)

    def __init__(self, arg1: Expr, args2: Expr, *args: Expr):
        flat_expr: list[Expr] = []
        for arg in chain((arg1, args2), args):
            if isinstance(arg, type(self)):
                flat_expr.extend(arg.arguments)
            else:
                flat_expr.append(arg)
        object.__setattr__(self, "arguments", tuple(flat_expr))

        post_init = getattr(self, "__post_init__", None)
        if post_init:
            post_init()

    @override
    def args(self):
        return self.arguments


def _validate(*validators: Callable[[Operator], None]):
    C = TypeVar("C", bound=Operator)

    def decorator(cls: type[C]) -> type[C]:
        if not is_dataclass(cls):
            raise ValueError("not is_dataclass(cls)")

        old_post_init = getattr(cls, "__post_init__", None)

        def new_post_init(self: C):
            if old_post_init:
                old_post_init(self)
            for validator in validators:
                validator(self)

        setattr(cls, "__post_init__", new_post_init)

        return cls

    return decorator


def _bound_args_sort(
    allowed_sorts: set[Sort] | None = None, forbidden_sorts: set[Sort] | None = None
) -> Callable[[Operator], None]:
    if allowed_sorts is not None and forbidden_sorts is not None:
        raise ValueError("allowed_sorts is not None and forbidden_sorts is not None")

    def validator(self: Operator):
        args = self.args()
        name = self.name()

        # check every sort is allowed
        for arg in args:
            if allowed_sorts is not None and sort_of(arg) not in allowed_sorts:
                raise ValueError(f"operator '{name}' accepts only instances of types {allowed_sorts}")
            if forbidden_sorts is not None and sort_of(arg) in forbidden_sorts:
                raise ValueError(f"operator '{name}' accepts no instances of types {forbidden_sorts}")

    return validator


def _all_args_same_sort(self: Operator):
    args = self.args()

    if len(args) <= 0:
        return
    first_arg, *args_tail = args
    for arg in args_tail:
        first_arg_sort = sort_of(first_arg)
        arg_sort = sort_of(arg)
        if first_arg_sort != arg_sort:
            raise ValueError(f"All arguments must be of the same type: expected {first_arg_sort}, found {arg_sort}")


def _arithmetic(op: Operator):
    _bound_args_sort({INT, REAL})(op)
    _all_args_same_sort(op)


def _boolean(op: Operator):
    _bound_args_sort({BOOL})(op)
    _all_args_same_sort(op)


def _only_pointers(op: Operator):
    for arg in op.args():
        if not sort_of(arg).is_ptr():
            raise ValueError("All arguments must be of pointer sort")
    _all_args_same_sort(op)


def _no_pointers(op: Operator):
    for arg in op.args():
        if sort_of(arg).is_ptr():
            raise ValueError("Pointer-sorted arguments are not allowed")
    _all_args_same_sort(op)


def _no_fields(op: Operator):
    for arg in op.args():
        match arg:
            case Field():
                raise ValueError("Fields are not allowed as arguments")
            case _ if isinstance(arg, Operator):
                _no_fields(arg)
            case _:
                pass


def _no_pointer_comparison(op: Operator):
    for arg in op.args():
        match arg:
            case PtrIsPtr():
                raise ValueError("pointers comparisons are not allowed as arguments")
            case _ if isinstance(arg, Operator):
                _no_pointer_comparison(arg)
            case _:
                pass


@dataclass(frozen=True)
@_validate(_only_pointers)
class PtrIsNil(_UnaryOperator):
    """Check whether a pointer expression is nil.

    Accepts a single pointer expression and returns a boolean-like operator.
    """

    def __post_init__(self):
        if not isinstance(self.argument, Var):
            raise ValueError("not isinstance(self.argument, Var)")

    @override
    def name(self) -> str:
        return "isnil"


@dataclass(frozen=True, slots=True)
@_validate(_only_pointers)
class PtrIsPtr(_BinaryOperator):
    """Check pointer identity between two pointer expressions.

    Used to compare two pointer-typed expressions for pointer equality.
    """

    def __post_init__(self):
        if not isinstance(self.left, (Var)):
            raise ValueError("not isinstance(self.left, Var)")

        if not isinstance(self.right, Var):
            raise ValueError("not isinstance(self.right, Var)")

    @override
    def name(self) -> str:
        return "is"


# deleted because hard to map into the knitted tree framwors
# @dataclass(frozen=True, slots=True)
# @_validate(_only_pointers)
# class FieldIsNil(_UnaryOperator):
#     """Check whether a field expression is nil.

#     Accepts a single field expression and returns a boolean-like operator.
#     """

#     def __post_init__(self):
#         if not isinstance(self.argument, Field):
#             raise ValueError("not isinstance(self.argument, Field)")

#     @override
#     def name(self) -> str:
#         return "isnil"


# @dataclass(frozen=True, slots=True)
# @_validate(_only_pointers)
# class FieldIsPtr(_BinaryOperator):
#     """Check pointer identity between a pointer expression and a field expression.

#     Used to compare a pointer-typed expression and a field-typed expression for pointer equality.
#     """

#     def __post_init__(self):
#         if not isinstance(self.left, Field):
#             raise ValueError("not isinstance(self.left, Field)")

#         if not isinstance(self.right, Var):
#             raise ValueError("not isinstance(self.right, Var)")

#     @override
#     def name(self) -> str:
#         return "is"


@dataclass(frozen=True, slots=True, init=False)
@_validate(_boolean, _no_fields, _no_pointer_comparison)
class And(_AssociativeOperator):
    """N-ary logical conjunction over boolean expressions.

    Requires at least two boolean arguments.
    """

    @override
    def name(self) -> str:
        return "and"


@dataclass(frozen=True, slots=True, init=False)
@_validate(_boolean, _no_fields, _no_pointer_comparison)
class Or(_AssociativeOperator):
    """N-ary logical disjunction over boolean expressions.

    Requires at least two boolean arguments.
    """

    @override
    def name(self) -> str:
        return "or"


@dataclass(frozen=True, slots=True)
@_validate(_boolean, _no_fields)
class Not(_UnaryOperator):
    """Logical negation of a boolean expression.

    Accepts a single boolean argument.
    """

    @override
    def name(self) -> str:
        return "not"


@dataclass(frozen=True, slots=True)
@_validate(_no_pointers, _no_fields)
class Eq(_BinaryOperator):
    """Equality comparison between two expressions of the same sort."""

    @override
    def name(self) -> str:
        return "="


@dataclass(frozen=True, slots=True)
@_validate(_no_pointers, _no_fields)
class Ne(_BinaryOperator):
    """Inequality comparison between two expressions of the same sort."""

    @override
    def name(self) -> str:
        return "!="


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Lt(_BinaryOperator):
    """Strict less-than comparison for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return "<"


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Le(_BinaryOperator):
    """Less-than-or-equal comparison for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return "<="


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Gt(_BinaryOperator):
    """Strict greater-than comparison for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return ">"


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Ge(_BinaryOperator):
    """Greater-than-or-equal comparison for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return ">="


@dataclass(frozen=True, slots=True, init=False)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Add(_AssociativeOperator):
    """N-ary addition for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return "+"


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Sub(_BinaryOperator):
    """Binary subtraction for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return "-"


@dataclass(frozen=True, slots=True, init=False)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Mul(_AssociativeOperator):
    """N-ary multiplication for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return "*"


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _all_args_same_sort, _no_fields)
class Div(_BinaryOperator):
    """Binary division for numeric expressions (int or real)."""

    @override
    def name(self) -> str:
        return "/"


@dataclass(frozen=True, slots=True)
@_validate(_bound_args_sort({INT}), _no_fields)
class Mod(_BinaryOperator):
    """Integer modulus operation; both operands must be integers."""

    @override
    def name(self) -> str:
        return "mod"


@dataclass(frozen=True, slots=True)
@_validate(_arithmetic, _no_fields)
class Negate(_UnaryOperator):
    """Numeric negation for integer or real expressions."""

    @override
    def name(self) -> str:
        return "neg"


_BoolExpr: TypeAlias = PtrIsNil | PtrIsPtr | Eq | Ne | Lt | Le | Ge | Gt | And | Or | Not | Var | Field

_NumExpr: TypeAlias = Add | Sub | Mul | Div | Mod | Negate | int | float | Var | Field

Expr: TypeAlias = (
    Add
    | Sub
    | Mul
    | Div
    | Mod
    | Negate
    | int
    | float
    | Var
    | Field
    | PtrIsNil
    | PtrIsPtr
    | Eq
    | Ne
    | Lt
    | Le
    | Ge
    | Gt
    | And
    | Or
    | Not
    | EnumConst
)


def sort_of(expr: Expr) -> Sort:
    match expr:
        case Var(_, sort):
            return sort
        case Field(Var(_, sort), name):
            return sort.pointee.fields[name].sort  # type: ignore
        case EnumConst(sort, _):
            return sort
        case int():
            return INT
        case float():
            return REAL
        case PtrIsNil() | PtrIsPtr() | Eq() | Ne() | Lt() | Le() | Ge() | Gt() | And() | Or() | Not():
            return BOOL
        case Add() | Sub() | Mul() | Div() | Mod() | Negate():
            return sort_of(expr.arg(0))
        case _:
            raise ValueError(f"Unknown expression type: {type(expr)}")


_EnvDomain = int | float | EnumConst | None
_Env = dict[Var | Field, _EnvDomain]


def _is_const(expr):
    return isinstance(expr, (int, float, EnumConst))


def _cast_to_ir_bool(b):
    return TRUE if b else FALSE


def _var_normalized(var, env):
    return env.get(var, var)


def _field_normalized(field, env):
    return env.get(field, field)


def _int_normalized(value, env):
    return value


def _float_normalized(value, env):
    return value


def _ptrisnil_normalized(ptrisnil, env):
    if ptrisnil.argument in env:
        return _cast_to_ir_bool(env[ptrisnil.argument] is None)
    else:
        return ptrisnil


def _ptrisptr_normalized(ptrisptr, env):
    if ptrisptr.left in env and ptrisptr.right in env:
        if env[ptrisptr.left] is None and env[ptrisptr.right] is None:
            return TRUE
        elif env[ptrisptr.left] == env[ptrisptr.right]:
            return TRUE
        else:
            return FALSE
    else:
        return ptrisptr


def _binary_operator_normalized(expr, env, cls, op):
    left = _normalized(expr.left, env)
    right = _normalized(expr.right, env)
    if _is_const(left) and _is_const(right):
        if sort_of(expr) == BOOL:
            return _cast_to_ir_bool(op(left, right))
        else:
            return op(left, right)
    else:
        return cls(left, right)


def _eq_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Eq, operator.eq)


def _ne_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Ne, operator.ne)


def _gt_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Gt, operator.gt)


def _ge_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Ge, operator.ge)


def _lt_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Lt, operator.lt)


def _le_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Le, operator.le)


def _sub_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Sub, operator.sub)


def _div_normalized(expr, env):
    if sort_of(expr) == INT:
        return _binary_operator_normalized(expr, env, Div, operator.floordiv)
    else:
        return _binary_operator_normalized(expr, env, Div, operator.truediv)


def _mod_normalized(expr, env):
    return _binary_operator_normalized(expr, env, Mod, operator.mod)


def _negate_normalized(expr, env):
    arg = _normalized(expr.argument, env)
    if _is_const(arg):
        return -arg
    else:
        return Negate(arg)


def _associative_operator_normalized(expr, env, cls, op, neutral_value, killer_value, death_result):
    normalized_args = [_normalized(arg, env) for arg in expr.args()]
    if killer_value is not None and killer_value in normalized_args:
        return death_result

    const_args = [arg for arg in normalized_args if _is_const(arg)]
    consts_eval = reduce(op, const_args, neutral_value)
    new_args = [arg for arg in normalized_args if not _is_const(arg)]

    if not new_args:
        return consts_eval

    if consts_eval != neutral_value:
        new_args.append(consts_eval)

    if len(new_args) == 1:
        return new_args[0]

    return cls(new_args[0], new_args[1], *new_args[2:])


def _add_normalized(expr: Add, env):
    return _associative_operator_normalized(expr, env, Add, operator.add, 0, None, None)


def _mul_normalized(expr: Mul, env):
    return _associative_operator_normalized(expr, env, Mul, operator.mul, 1, 0, 0)


def _and_normalized(expr, env):
    def and_op(left, right):
        return TRUE if left == TRUE and right == TRUE else FALSE

    return _associative_operator_normalized(expr, env, And, and_op, TRUE, FALSE, FALSE)


def _or_normalized(expr, env):
    def or_op(left, right):
        return TRUE if left == TRUE or right == TRUE else FALSE

    return _associative_operator_normalized(expr, env, Or, or_op, FALSE, TRUE, TRUE)


def _not_normalized(expr, env):
    arg = _normalized(expr.argument, env)
    if _is_const(arg):
        if arg == TRUE:
            return FALSE
        elif arg == FALSE:
            return TRUE
    elif arg == expr:
        return Not(arg)
    else:
        return _normalized(Not(arg))


def normalized(expr: Expr, env: dict[Expr, int | float | EnumConst | None]) -> Expr:
    if expr in env:
        return env[expr]
    match expr:
        case Var():
            return _var_normalized(expr, env)
        case Field():
            return _field_normalized(expr, env)
        case int():
            return _int_normalized(expr, env)
        case float():
            return _float_normalized(expr, env)
        case EnumConst():
            return expr
        case Not(Not(e)):
            return _normalized(e, env)
        case Not():
            return _not_normalized(expr, env)
        case And():
            return _and_normalized(expr, env)
        case Or():
            return _or_normalized(expr, env)
        case Eq():
            return _eq_normalized(expr, env)
        case Ne():
            return _ne_normalized(expr, env)
        case Lt():
            return _lt_normalized(expr, env)
        case Le():
            return _le_normalized(expr, env)
        case Gt():
            return _gt_normalized(expr, env)
        case Ge():
            return _ge_normalized(expr, env)
        case Add():
            return _add_normalized(expr, env)
        case Sub():
            return _sub_normalized(expr, env)
        case Mul():
            return _mul_normalized(expr, env)
        case Div():
            return _div_normalized(expr, env)
        case Mod():
            return _mod_normalized(expr, env)
        case Negate():
            return _negate_normalized(expr, env)
        case PtrIsNil():
            return _ptrisnil_normalized(expr, env)
        case PtrIsPtr():
            return _ptrisptr_normalized(expr, env)
        case _:
            raise ValueError(f"Unknown expression type: {type(expr)}")
