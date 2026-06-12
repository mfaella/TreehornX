from treehornx.ir.expressions import Var
from treehornx.ir.function import Function
from treehornx.parser._internal.cparser.errors import CParserError
from treehornx.parser.CParser import CParser
from treehornx.ux.tui import error


def handle_function_parsing(input_file: str, function_name: str | None) -> Function | None:
    parser = CParser()
    try:
        functions_iterator = iter(parser.parse_file(input_file))
    except CParserError as e:
        error(f"Error parsing {input_file}: {e}")
        return None
    if function_name is None:
        function = next(functions_iterator, None)
    else:
        function = next(
            (f for f in functions_iterator if f.name == function_name),
            None,
        )
    if function is None:
        error(f"Function {function_name} not found in {input_file}.")
    return function


def handle_root_fetching(function: Function, root_name: str) -> Var | None:
    root = next((var for var in function.vars if var.name == root_name), None)
    if root is None:
        error(f"Root variable {root_name} not found in function {function.name}.")
    return root
