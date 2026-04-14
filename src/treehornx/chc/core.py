from enum import Enum

class ExitCodeKind(Enum):
    ERR = 1
    OOM = 2
    LABEL_OVERFLOW = 3
    CLEAN = 0
