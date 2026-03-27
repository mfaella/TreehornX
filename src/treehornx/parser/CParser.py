import io
from typing import Iterable, TextIO, override

from pycparser.c_parser import ParseError

from treehornx.ir.function import Function

from ._internal.cparser import errors as err
from ._internal.cparser.FileVisitor import FileVisitor
from .Parser import Parser


CParserError = err.CParserError
UnsupportedFeatureError = err.UnsupportedFeatureError
UnknownTypeError = err.UnknownTypeError
DuplicateDefinitionError = err.DuplicateDefinitionError
UndefinedSymbolError = err.UndefinedSymbolError


class CParser(Parser):
    @override
    def parse(self, input_text: TextIO) -> Iterable[Function]:
        try:
            ast = FileVisitor.produce_ast_from_textio(input_text)
            file_visitor = FileVisitor()
            file_visitor.visit(ast)
        except ParseError as e:
            raise CParserError(None, str(e))
        except Exception as e:
            raise e
        return file_visitor.functions.values()

    @override
    def parse_src(self, input_text: str) -> Iterable[Function]:
        return self.parse(io.StringIO(input_text))

    @override
    def parse_file(self, file_path: str) -> Iterable[Function]:
        with open(file_path, "r") as file:
            return self.parse(file)
