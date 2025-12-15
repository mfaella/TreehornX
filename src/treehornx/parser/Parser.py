from typing import Iterable, Protocol, TextIO

from treehornx.ir.function import Function

from ._internal.cparser.errors import *


class Parser(Protocol):
    def parse_src(self, input_text: str) -> Iterable[Function]: ...

    def parse(self, input_text: TextIO) -> Iterable[Function]: ...

    def parse_file(self, file_path: str) -> Iterable[Function]: ...
