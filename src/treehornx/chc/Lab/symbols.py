"""SMT symbols of the Lab CHC system.

The data of the frame at position `index` of a label are encoded by the symbols
`<prefix>v<id>_<index>` for the data variable `id` and `<prefix>f<id>_<index>` for the data
field `id`. Every internal chain of a label is compressed to its first and last frame (see
`kept_frames`), so a predicate only receives the symbols of the kept frames.
"""

from typing import Callable

import pychc.shortcuts as chc
import pysmt.shortcuts as smt
import pysmt.typing as smtty
from pysmt.fnode import FNode

from treehornx import ir
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.Lab import Lab
from treehornx.enum_models.Lab.helpers import prev_of


def smt_type(data_type: ir.DataType) -> smtty.PySMTType:
    match data_type:
        case ir.DataType.INT:
            return smtty.INT
        case ir.DataType.BOOL:
            return smtty.BOOL


def var_symbol(function: ir.Function, var_id: int, index: int, prefix: str = "") -> FNode:
    return smt.Symbol(f"{prefix}v{var_id}_{index}", smt_type(function.data_var_type(var_id)))


def field_symbol(function: ir.Function, field_id: int, index: int, prefix: str = "") -> FNode:
    return smt.Symbol(f"{prefix}f{field_id}_{index}", smt_type(function.data_field_type(field_id)))


def var_symbols(function: ir.Function, index: int, prefix: str = "") -> list[FNode]:
    return [var_symbol(function, v.id, index, prefix) for v in function.data_vars]


def field_symbols(function: ir.Function, index: int, prefix: str = "") -> list[FNode]:
    return [field_symbol(function, f.id, index, prefix) for f in function.node.data_fields]


def frame_symbols(function: ir.Function, index: int, prefix: str = "") -> list[FNode]:
    return var_symbols(function, index, prefix) + field_symbols(function, index, prefix)


def _is_internal_frame(label: Lab, i: int) -> bool:
    prev = prev_of(label, i)
    return prev is not None and prev[0] == Internal()


def kept_frames(label: Lab) -> list[int]:
    """Positions of the frames whose data are arguments of the predicate of `label`.

    A frame is dropped when it is both reached and left by an internal step, i.e. when it is an
    intermediate frame of an internal chain. Frames linked to other nodes are always kept."""
    a = len(label)
    return [
        i for i in range(1, a + 1) if i == a or not (_is_internal_frame(label, i) and _is_internal_frame(label, i + 1))
    ]


def label_symbols(function: ir.Function, label: Lab, prefix: str = "") -> list[FNode]:
    return [s for i in kept_frames(label) for s in frame_symbols(function, i, prefix)]


def predicate_name(label: Lab) -> str:
    return f"Lab{label.id}"


def frame_types(function: ir.Function) -> list[smtty.PySMTType]:
    return [smt_type(v.type) for v in function.data_vars] + [smt_type(f.type) for f in function.node.data_fields]


def predicate(function: ir.Function, label: Lab) -> FNode:
    return chc.Predicate(predicate_name(label), [t for _ in kept_frames(label) for t in frame_types(function)])


def apply(function: ir.Function, label: Lab, prefix: str = "") -> FNode:
    return chc.Apply(predicate(function, label), label_symbols(function, label, prefix))


_BINARY_OPS: dict[str, Callable[[FNode, FNode], FNode]] = {
    "+": smt.Plus,
    "-": smt.Minus,
    "*": smt.Times,
    "/": chc.IntDiv,
    "%": chc.Mod,
    "<": smt.LT,
    "<=": smt.LE,
    ">": smt.GT,
    ">=": smt.GE,
    "==": smt.EqualsOrIff,
    "!=": lambda left, right: smt.Not(smt.EqualsOrIff(left, right)),
    "&&": smt.And,
    "||": smt.Or,
}


def expr_to_smt(function: ir.Function, expr: ir.DataExpr, index: int, prefix: str = "") -> FNode:
    """`expr` with every data variable evaluated at the frame `index`."""
    match expr:
        case ir.Const(value, ir.DataType.BOOL):
            return smt.Bool(bool(value))
        case ir.Const(value, ir.DataType.INT):
            return smt.Int(int(value))
        case ir.Var(var_id):
            return var_symbol(function, var_id, index, prefix)
        case ir.UnOp("-", operand):
            return smt.Minus(smt.Int(0), expr_to_smt(function, operand, index, prefix))
        case ir.UnOp("!", operand):
            return smt.Not(expr_to_smt(function, operand, index, prefix))
        case ir.BinOp(op, left, right) if op in _BINARY_OPS:
            return _BINARY_OPS[op](
                expr_to_smt(function, left, index, prefix), expr_to_smt(function, right, index, prefix)
            )
        case _:
            raise NotImplementedError(f"Unsupported data expression: {expr}")
