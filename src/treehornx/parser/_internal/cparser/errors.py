C_SUBSET_DOC_LINK = "<link>"


class CParserError(Exception):
    def __init__(self, line: int, message: str):
        super().__init__(f"line: {line} >>> {message}")


class UnsupportedFeatureError(CParserError):
    """Raised when an unsupported C feature is encountered."""

    def __init__(self, line: int, msg: str):
        super().__init__(line, f"Unsupported C subset feature, look at {C_SUBSET_DOC_LINK} for details: {msg}")


class UnknownTypeError(CParserError):
    """Raised when an unknown type is encountered."""

    def __init__(self, line: int, type_name: str):
        super().__init__(line, f"Unknown type encountered: {type_name}")


class DuplicateDefinitionError(CParserError):
    """Raised when a duplicate definition is encountered."""

    def __init__(self, line: int, name: str):
        super().__init__(line, f"Duplicate definition encountered: {name}")


class UndefinedSymbolError(CParserError):
    """Raised when an undefined symbol is encountered."""

    def __init__(self, line: int, name: str):
        super().__init__(line, f"Undefined symbol encountered: {name}")
