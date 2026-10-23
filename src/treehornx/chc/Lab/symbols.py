"""SMT symbols of the Lab CHC system.

The data of the frame at position `index` of a label are encoded by the symbols
`<prefix>v<id>_<index>` for the data variable `id` and `<prefix>f<id>_<index>` for the data
field `id`. Every internal chain of a label is compressed to its first and last frame (see
`kept_frames`), so a predicate only receives the symbols of the kept frames.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from treehornx import ir
from treehornx.chc.smt import sexpr as sx
from treehornx.enum_models.core.Dir import Internal
from treehornx.enum_models.core.InternedPool import InternedPool
from treehornx.enum_models.Lab import Lab
from treehornx.enum_models.Lab.LabEngine import LabEngine


@dataclass
class ChcLabUtils:
    function: ir.Function
    engine: LabEngine
    # every prefix of a label is a predicate, but the engine only interns the ends of internal chains
    _predicate_ids: InternedPool[Lab] = field(default_factory=InternedPool[Lab], init=False)
    # internal_constraints of every (label, symbol prefix), built on the entry of the label's prefix
    internal_constraints_cache: dict[tuple[Lab, str], tuple[sx.SExpr, ...]] = field(
        default_factory=dict[tuple[Lab, str], tuple[sx.SExpr, ...]], init=False
    )

    def smt_type(self, data_type: ir.DataType) -> sx.Type:
        match data_type:
            case ir.DataType.INT:
                return sx.Type.Int
            case ir.DataType.BOOL:
                return sx.Type.Bool

    def var_symbol(self, var_id: int, index: int, prefix: str = "") -> sx.Var:
        return sx.Var(f"{prefix}v{var_id}_{index}", self.smt_type(self.function.data_var_type(var_id)))

    def field_symbol(self, field_id: int, index: int, prefix: str = "") -> sx.Var:
        return sx.Var(f"{prefix}f{field_id}_{index}", self.smt_type(self.function.data_field_type(field_id)))

    def var_symbols(self, index: int, prefix: str = "") -> list[sx.Var]:
        return [self.var_symbol(v.id, index, prefix) for v in self.function.data_vars]

    def field_symbols(self, index: int, prefix: str = "") -> list[sx.Var]:
        return [self.field_symbol(f.id, index, prefix) for f in self.function.node.data_fields]

    def frame_symbols(self, index: int, prefix: str = "") -> list[sx.Var]:
        return self.var_symbols(index, prefix) + self.field_symbols(index, prefix)

    def _is_internal_frame(self, label: Lab, i: int) -> bool:
        return label[i].prev == Internal()

    def kept_frames(self, label: Lab) -> list[int]:
        """Positions of the frames whose data are arguments of the predicate of `label`.

        A frame is dropped when it is both reached and left by an internal step, i.e. when it is an
        intermediate frame of an internal chain. Frames linked to other nodes are always kept."""
        a = len(label)
        return [
            i
            for i in range(1, a + 1)
            if i == a or not (self._is_internal_frame(label, i) and self._is_internal_frame(label, i + 1))
        ]

    def label_symbols(self, label: Lab, prefix: str = "") -> list[sx.Var]:
        return [s for i in self.kept_frames(label) for s in self.frame_symbols(i, prefix)]

    def _label_id(self, label: Lab) -> int:
        self._predicate_ids.intern(label)
        return self._predicate_ids.get_id(label)

    def predicate_name(self, label: Lab) -> str:
        return f"Lab{self._label_id(label)}"

    def frame_types(self) -> list[sx.Type]:
        return [self.smt_type(v.type) for v in self.function.data_vars] + [
            self.smt_type(f.type) for f in self.function.node.data_fields
        ]

    def predicate(self, label: Lab) -> sx.Predicate:
        return sx.Predicate(
            self.predicate_name(label), [t for _ in self.kept_frames(label) for t in self.frame_types()]
        )

    def apply(self, label: Lab, prefix: str = "") -> sx.Application:
        return sx.Application(self.predicate(label), *self.label_symbols(label, prefix))

    _BINARY_OPS: ClassVar[dict[str, sx.Operator]] = {
        "+": sx.Operator.ADD,
        "-": sx.Operator.SUB,
        "*": sx.Operator.MUL,
        "/": sx.Operator.DIV,
        "%": sx.Operator.MOD,
        "<": sx.Operator.LT,
        "<=": sx.Operator.LE,
        ">": sx.Operator.GT,
        ">=": sx.Operator.GE,
        "==": sx.Operator.EQ,
        "&&": sx.Operator.AND,
        "||": sx.Operator.OR,
    }

    def expr_to_smt(self, expr: ir.DataExpr, index: int, prefix: str = "") -> sx.SExpr:
        """`expr` with every data variable evaluated at the frame `index`."""
        match expr:
            case ir.Const(value, ir.DataType.BOOL):
                return sx.Constant(bool(value))
            case ir.Const(value, ir.DataType.INT):
                return sx.Constant(int(value))
            case ir.Var(var_id):
                return self.var_symbol(var_id, index, prefix)
            case ir.UnOp("-", operand):
                return sx.OpExpr(sx.Operator.SUB, 0, self.expr_to_smt(operand, index, prefix))
            case ir.UnOp("!", operand):
                return sx.OpExpr(sx.Operator.NOT, self.expr_to_smt(operand, index, prefix))
            case ir.BinOp("!=", left, right):
                return sx.OpExpr(
                    sx.Operator.NOT,
                    sx.OpExpr(
                        sx.Operator.EQ, self.expr_to_smt(left, index, prefix), self.expr_to_smt(right, index, prefix)
                    ),
                )
            case ir.BinOp(op, left, right) if op in self._BINARY_OPS:
                return sx.OpExpr(
                    self._BINARY_OPS[op], self.expr_to_smt(left, index, prefix), self.expr_to_smt(right, index, prefix)
                )
            case _:
                raise NotImplementedError(f"Unsupported data expression: {expr}")
