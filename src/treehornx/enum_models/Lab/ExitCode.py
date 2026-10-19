from enum import Enum


class ExitCode(Enum):
    N = 0  # None
    C = 1  # Clean
    M = 2  # Memory
    E = 3  # Error
    O = 4  # Overflow
