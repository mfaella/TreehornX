from ir.sorts import Enum, Sort
from pycparser import c_ast

from .errors import DuplicateDefinitionError, UnsupportedFeatureError


class EnumDeclVisitor(c_ast.Node):
    def visit(self, node: c_ast.Enum):
        assert isinstance(node, c_ast.Enum)
        enum_name: str = node.name
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
            if enumerator.value is not None:
                raise UnsupportedFeatureError(
                    enumerator.coord.line,
                    f"Enum value '{enumerator_name}' is not supported.",
                )
            if enumerator.value:
                enumerator_value = int(enumerator.value.value)
            enum_values[enumerator_name] = enumerator_value
            enumerator_value_counter = enumerator_value + 1

        enum_sort = Enum(enum_name, enum_values)
        return enum_sort
