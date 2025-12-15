from typing import Iterable, TextIO, override

from treehornx.ir.function import Function

from ._internal.cparser.FileVisitor import FileVisitor
from .Parser import Parser


class CParser(Parser):
    @override
    def parse(self, input_text: TextIO) -> Iterable[Function]:
        ast = FileVisitor.produce_ast_from_textio(input_text)
        file_visitor = FileVisitor()
        file_visitor.visit(ast)
        return file_visitor.functions.values()

    @override
    def parse_src(self, input_text: str) -> Iterable[Function]:
        ast = FileVisitor.produce_ast_from_src(input_text)
        file_visitor = FileVisitor()
        file_visitor.visit(ast)
        return file_visitor.functions.values()

    @override
    def parse_file(self, file_path: str) -> Iterable[Function]:
        with open(file_path, "r") as file:
            return self.parse(file)
