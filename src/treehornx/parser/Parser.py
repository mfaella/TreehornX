from typing import Iterable, Protocol, TextIO

from ir.function import Function


class Parser(Protocol):
    def parse(self, input_text: TextIO) -> Iterable[Function]: ...

    def parse_file(self, file_path: str) -> Iterable[Function]: ...
