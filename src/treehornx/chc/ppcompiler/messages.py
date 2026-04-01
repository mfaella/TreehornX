MESSAGE_LIMIT = 20


def format_message(message: str) -> str:
    if len(message) > MESSAGE_LIMIT:
        return message[:MESSAGE_LIMIT] + "..."
    else:
        return message


class PrePostCompilerMessage:
    def __init__(self, line: int, column: int, message: str, file_name: str | None = None):
        formatted_message = format_message(message)
        f"{file_name or ''}:{line}:{column}:{formatted_message}"
        self.line = line
        self.column = column
        self.file_name = file_name


class PrePostCompilerError(PrePostCompilerMessage):
    def __init__(self, line: int, column: int, message: str, file_name: str | None = None):
        super().__init__(line, column, message, file_name)


class PrePostCompilerWarning(PrePostCompilerMessage):
    def __init__(self, line: int, column: int, message: str, file_name: str | None = None):
        super().__init__(line, column, message, file_name)


class UnknownProgramSymbolError(PrePostCompilerError):
    def __init__(self, line: int, column: int, variable_name: str, file_name: str | None = None):
        super().__init__(line, column, f"'{variable_name}' not found in program scope", file_name)
        self.variable_name = variable_name


class ForbiddenNameShadowingError(PrePostCompilerError):
    def __init__(
        self, line: int, column: int, variable_name: str, prev_line: int, prev_column: int, file_name: str | None = None
    ):
        super().__init__(
            line,
            column,
            f"'{variable_name}' shadows a symbol previously defined at {prev_line}:{prev_column}",
            file_name,
        )
        self.variable_name = variable_name
        self.prev_line = prev_line
        self.prev_column = prev_column


class UnknownSymbolError(PrePostCompilerError):
    def __init__(self, line: int, column: int, symbol_name: str, file_name: str | None = None):
        super().__init__(line, column, f"'{symbol_name}' not found in scope", file_name)
        self.symbol_name = symbol_name


class UnusedParameterWarning(PrePostCompilerWarning):
    def __init__(self, line: int, column: int, parameter_name: str, file_name: str | None = None):
        super().__init__(line, column, f"Parameter '{parameter_name}' is never used", file_name)
        self.parameter_name = parameter_name


class MacroExpansionMissingParametersError(PrePostCompilerError):
    def __init__(
        self,
        line: int,
        column: int,
        macro_name: str,
        expected_params: int,
        actual_params: int,
        file_name: str | None = None,
    ):
        super().__init__(
            line,
            column,
            f"Macro '{macro_name}' expects {expected_params} parameters but got {actual_params}",
            file_name,
        )
        self.macro_name = macro_name
        self.expected_params = expected_params
        self.actual_params = actual_params


class MacroExpansionTooManyParametersError(PrePostCompilerError):
    def __init__(
        self,
        line: int,
        column: int,
        macro_name: str,
        expected_params: int,
        actual_params: int,
        file_name: str | None = None,
    ):
        super().__init__(
            line,
            column,
            f"Macro '{macro_name}' expects {expected_params} parameters but got {actual_params}",
            file_name,
        )
        self.macro_name = macro_name
        self.expected_params = expected_params
        self.actual_params = actual_params


class MacroExpansionParameterTypeError(PrePostCompilerError):
    def __init__(
        self,
        line: int,
        column: int,
        macro_name: str,
        param_index: int,
        expected_type: str,
        actual_type: str,
        file_name: str | None = None,
    ):
        super().__init__(
            line,
            column,
            f"Macro '{macro_name}' parameter {param_index} expects type {expected_type} but got {actual_type}",
            file_name,
        )
        self.macro_name = macro_name
        self.param_index = param_index
        self.expected_type = expected_type
        self.actual_type = actual_type


class TypeSymbolUsedAsIdentifierError(PrePostCompilerError):
    def __init__(self, line: int, column: int, symbol_name: str, file_name: str | None = None):
        super().__init__(line, column, f"Type symbol '{symbol_name}' cannot be used as an identifier", file_name)
        self.symbol_name = symbol_name


class TypeMismatchError(PrePostCompilerError):
    def __init__(self, line: int, column: int, expected_type: str, actual_type: str, file_name: str | None = None):
        super().__init__(line, column, f"Expected type {expected_type} but got {actual_type}", file_name)
        self.expected_type = expected_type
        self.actual_type = actual_type


class TypeInferenceError(PrePostCompilerError):
    def __init__(self, line: int, column: int, name: str, file_name: str | None = None):
        super().__init__(line, column, f"Impossible to infer type for expression '{name}'", file_name)
        self.name = name


class TypeInferenceConflictError(PrePostCompilerError):
    def __init__(self, line: int, column: int, name: str, inferred_type: str, file_name: str | None = None):
        super().__init__(line, column, f"Type of {name} was already inferred to {inferred_type}", file_name)
        self.name = name

class UnknownFieldError(PrePostCompilerError):
    def __init__(self, line: int, column: int, field_name: str, file_name: str | None = None):
        super().__init__(line, column, f"Unknown field '{field_name}'", file_name)
        self.field_name = field_name
