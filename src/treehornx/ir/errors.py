class IRError(Exception):
    """Base class for all IR-related errors."""

    def __init__(self, message: str):
        super().__init__(f"IR Error: {message}")


class IncompatibleReturnTypeError(IRError):
    """Raised when a function's return type is incompatible with the expected type."""

    def __init__(self, msg: str):
        super().__init__(msg)
