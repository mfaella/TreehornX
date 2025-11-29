from unittest import TestCase

from ir.expressions import Var
from ir.sorts import BOOL, INT, REAL, Enum, Pointer, Struct
from parser._internal.cparser.CASTVisitor import CASTVisitor
from parser._internal.cparser.errors import DuplicateDefinitionError, UnknownTypeError, UnsupportedFeatureError


class TestCASTVisitor(TestCase):
    # valid structure
    def test_parse_Point_struct(self):
        code = """
        struct Point {
            float x;
            float y;
            struct Point* next;
        };
        """

        ast = CASTVisitor.produce_ast_from_src(code)
        visitor = CASTVisitor()
        visitor.visit(ast)

        self.assertIn("Point", visitor.sorts)

        struct = visitor.sorts["Point"]
        self.assertIsInstance(struct, Struct)
        self.assertEqual(struct.name, "Point")
        self.assertEqual(struct.fields["x"], Var("x", REAL))
        self.assertEqual(struct.fields["y"], Var("y", REAL))

    # valid structure with pointer to itself
    def test_parse_RBTree_struct(self):
        code = """
        #include <stdbool.h>

        struct RBTree {
            int value;
            _Bool is_red;
            struct RBTree* left;
            struct RBTree* right;
        };
        """

        ast = CASTVisitor.produce_ast_from_src(code)
        visitor = CASTVisitor()
        visitor.visit(ast)

        self.assertIn("RBTree", visitor.sorts)

        struct = visitor.sorts["RBTree"]

        self.assertEqual(struct.name, "RBTree")
        self.assertEqual(struct.fields["value"], Var("value", INT))
        self.assertEqual(struct.fields["is_red"], Var("is_red", BOOL))
        self.assertEqual(struct.fields["left"], Var("left", Pointer(struct)))
        self.assertEqual(struct.fields["right"], Var("right", Pointer(struct)))

    def test_duplicate_struct_definition(self):
        code = """
        struct Point {
            float x;
            float y;
            struct Point* next;
        };
        struct Point {
            int z;
            struct Point* next;
        };
        """
        with self.assertRaises(DuplicateDefinitionError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_parse_anonymous_struct(self):
        code = """
        struct {
            int x;
            int y;
        } point;
        """

        with self.assertRaises(UnsupportedFeatureError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_inner_anonyomous_struct_field(self):
        code = """
        struct Point{
            struct { float x; float y; } point;
            int z;
        };
        """

        with self.assertRaises(UnsupportedFeatureError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_inner_struct_field(self):
        code = """
        struct LL {
            int value;
            struct LL* next;
        }

        struct BST {
            struct LL* nums;
            struct BST* left;
            struct BST* right;
        };
        """

        with self.assertRaises(UnsupportedFeatureError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_inner_struct_field(self):
        code = """
        struct LL {
            int value;
            struct LL* next;
        } l;
        """

        with self.assertRaises(UnsupportedFeatureError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_non_struct_ptr_field(self):
        code = """
        struct {
            int *a;
            int z;
        };
        """

        with self.assertRaises(UnsupportedFeatureError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_field_name_duplication(self):
        code = """
        struct Point {
            int a;
            float a;
        };
        """

        with self.assertRaises(DuplicateDefinitionError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_field_name_duplication_with_pointer(self):
        code = """
        struct MyStruct {
            int a;
            struct MyStruct* a;
        };
        """

        with self.assertRaises(DuplicateDefinitionError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_unvalued_enum(self):
        code = """
        enum Color {
            RED,
            GREEN,
            BLUE
        };
        """
        ast = CASTVisitor.produce_ast_from_src(code)
        visitor = CASTVisitor()
        visitor.visit(ast)

        enum = visitor.sorts["Color"]
        self.assertIsInstance(enum, Enum)
        self.assertEqual(enum.name, "Color")
        self.assertEqual(len(enum.flags), 3)
        self.assertEqual(enum.flags["RED"], 0)
        self.assertEqual(enum.flags["GREEN"], 1)
        self.assertEqual(enum.flags["BLUE"], 2)

    def test_valued_enum(self):
        code = """
        enum Color {
            RED = 12,
            GREEN = 7,
            BLUE = 10000
        };
        """
        ast = CASTVisitor.produce_ast_from_src(code)
        visitor = CASTVisitor()
        visitor.visit(ast)

        enum = visitor.sorts["Color"]
        self.assertIsInstance(enum, Enum)
        self.assertEqual(enum.name, "Color")
        self.assertEqual(len(enum.flags), 3)
        self.assertEqual(enum.flags["RED"], 12)
        self.assertEqual(enum.flags["GREEN"], 7)
        self.assertEqual(enum.flags["BLUE"], 10_000)

    def test_partially_valued_enum(self):
        code = """
        enum Color {
            RED,
            ORANGE = 32,
            YELLOW,
            GREEN = 33,
            CYAN = 45,
            BLUE
        };
        """
        ast = CASTVisitor.produce_ast_from_src(code)
        visitor = CASTVisitor()
        visitor.visit(ast)

        enum = visitor.sorts["Color"]
        self.assertIsInstance(enum, Enum)
        self.assertEqual(enum.name, "Color")
        self.assertEqual(len(enum.flags), 6)
        self.assertEqual(enum.flags["RED"], 0)
        self.assertEqual(enum.flags["ORANGE"], 32)
        self.assertEqual(enum.flags["YELLOW"], 33)
        self.assertEqual(enum.flags["GREEN"], 33)
        self.assertEqual(enum.flags["CYAN"], 45)
        self.assertEqual(enum.flags["BLUE"], 46)

    def test_enum_name_duplication(self):
        code = """
        enum Color {
            RED,
            GREEN,
            BLUE
        };

        enum Color {
            YELLOW,
            ORANGE
        };
        """

        with self.assertRaises(DuplicateDefinitionError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_enum_value_duplication(self):
        code = """
        enum Color {
            RED = 1,
            RED = 2,
            BLUE = 3
        };
        """

        with self.assertRaises(DuplicateDefinitionError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_anonymous_enum(self):
        code = """
        enum {
            RED = 1,
            GREEN = 2,
            BLUE = 3
        } Color;
        """

        with self.assertRaises(UnsupportedFeatureError):
            ast = CASTVisitor.produce_ast_from_src(code)
            visitor = CASTVisitor()
            visitor.visit(ast)

    def test_struct_with_enum_field(self):
        code = """
        enum Color {
            RED, BLACK
        };

        struct RBTree {
            enum Color color;
            struct RBTree* left;
            struct RBTree* right;
        };
        """

        ast = CASTVisitor.produce_ast_from_src(code)
        visitor = CASTVisitor()
        visitor.visit(ast)

        Color = visitor.sorts["Color"]
        RBTree = visitor.sorts["RBTree"]

        self.assertIsInstance(Color, Enum)
        self.assertIs(RBTree.fields["color"].sort, Color)

        self.assertIsInstance(RBTree, Struct)
        self.assertEqual(RBTree.fields["left"], Var("left", Pointer(RBTree)))
        self.assertEqual(RBTree.fields["right"], Var("right", Pointer(RBTree)))
