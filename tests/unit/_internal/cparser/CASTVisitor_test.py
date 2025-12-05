from unittest import TestCase

from ir.expressions import Add, And, Div, Eq, Ge, Gt, Le, Lt, Mod, Mul, Ne, Not, Or, PtrIsNil, PtrIsPtr, Sub, Var
from ir.instructions import Goto, IfGoto, Return, Skip, VarAssignExpr
from ir.sorts import BOOL, INT, REAL, UNIT, Enum, Pointer, Struct
from parser._internal.cparser.errors import DuplicateDefinitionError, UnknownTypeError, UnsupportedFeatureError
from parser._internal.cparser.FileVisitor import FileVisitor


class TestCASTVisitor(TestCase):
    def visit(self, code: str) -> FileVisitor:
        ast = FileVisitor.produce_ast_from_src(code)
        visitor = FileVisitor()
        visitor.visit(ast)
        return visitor

    def visit_raises(self, code: str, exc: type[Exception]) -> None:
        with self.assertRaises(exc):
            return self.visit(code)

    # valid structure
    def test_parse_Point_struct(self):
        code = """
        struct Point {
            float x;
            float y;
            struct Point* next;
        };
        """

        visitor = self.visit(code)

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

        visitor = self.visit(code)

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
        self.visit_raises(code, DuplicateDefinitionError)

    def test_struct_with_int_ptr_field(self):
        code = """
        struct MyStruct {
            int *a;
            struct MyStruct* next;
        };
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_other_struct_ptr_field(self):
        code = """
        struct OtherStruct {
            int value;
            struct OtherStruct* next;
        };

        struct MyStruct {
            struct OtherStruct* other;
            struct MyStruct* next;
        };
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_unknown_type_in_struct_field(self):
        code = """
        struct MyStruct {
            float x;
            unsigned int y;
            struct MyStruct* next;
        };
        """
        self.visit_raises(code, UnknownTypeError)

    def test_empty_struct(self):
        code = """
        struct EmptyStruct {};
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_no_struct_ptr_struct(self):
        code = """
        struct NoPtrStruct {
            int a;
            float b;
        };
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_parse_anonymous_struct(self):
        code = """
        struct {
            int x;
            int y;
        } point;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_struct_with_no_fields(self):
        code = """
        struct Empty;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_inner_anonyomous_struct_field(self):
        code = """
        struct Point{
            struct { float x; float y; } point;
            int z;
        };
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_inner_struct_field(self):
        code = """
        struct LL {
            int value;
            struct LL* next;
        };

        struct BST {
            struct LL* nums;
            struct BST* left;
            struct BST* right;
        };
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_struct_instance_decl_field(self):
        code = """
        struct LL {
            int value;
            struct LL* next;
        } l;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_non_struct_ptr_field(self):
        code = """
        struct {
            int *a;
            int z;
        };
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_field_name_duplication(self):
        code = """
        struct Point {
            int a;
            float a;
        };
        """

        self.visit_raises(code, DuplicateDefinitionError)

    def test_field_name_duplication_with_pointer(self):
        code = """
        struct MyStruct {
            int a;
            struct MyStruct* a;
        };
        """

        self.visit_raises(code, DuplicateDefinitionError)

    def test_unvalued_enum(self):
        code = """
        enum Color {
            RED,
            GREEN,
            BLUE
        };
        """
        visitor = self.visit(code)

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
        self.visit_raises(code, UnsupportedFeatureError)

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
        self.visit_raises(code, UnsupportedFeatureError)

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

        self.visit_raises(code, DuplicateDefinitionError)

    def test_enum_value_duplication(self):
        code = """
        enum Color {
            RED,
            RED,
            BLUE
        };
        """

        self.visit_raises(code, DuplicateDefinitionError)

    def test_anonymous_enum(self):
        code = """
        enum {
            RED,
            GREEN,
            BLUE
        } Color;
        """

        self.visit_raises(code, UnsupportedFeatureError)

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

        visitor = self.visit(code)

        Color = visitor.sorts["Color"]
        RBTree = visitor.sorts["RBTree"]

        self.assertIsInstance(Color, Enum)
        self.assertIs(RBTree.fields["color"].sort, Color)

        self.assertIsInstance(RBTree, Struct)
        self.assertEqual(RBTree.fields["left"], Var("left", Pointer(RBTree)))
        self.assertEqual(RBTree.fields["right"], Var("right", Pointer(RBTree)))

    def test_struct_with_anonymous_enum_field(self):
        code = """
        struct MyStruct {
            enum {
                RED, GREEN, BLUE
            } color;
            struct MyStruct* next;
        };
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_float_enum_values(self):
        code = """
        enum Color {
            RED = 0.0,
            GREEN,
            BLUE
        };
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_string_enum_values(self):
        code = """
        enum Color {
            RED = "RED",
            GREEN,
            BLUE
        };
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_char_enum_values(self):
        code = """
        enum Color {
            RED = 'r',
            GREEN,
            BLUE
        };
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_int_global_variable(self):
        code = """
        int x;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_enum_global_variable(self):
        code = """
        enum Color {
            RED,
            GREEN,
            BLUE
        };

        enum Color favorite_color;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_struct_global_variable(self):
        code = """
        struct Color {
            int red;
            int green;
            int blue;
        };

        struct Color favorite_color;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_struct_ptr_global_variable(self):
        code = """
        struct Color {
            int red;
            int green;
            int blue;
        };

        struct Color* favorite_color;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_typedef_int(self):
        code = """
        typedef int my_int;
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_typedef_struct(self):
        code = """
        typedef struct Point {
            float x;
            float y;
        } Point;
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_function_declaration(self):
        code = """
        int add(int a, int b);
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_union_definition(self):
        code = """
        union Data {
            int i;
            float f;
        } u;
        """
        self.visit_raises(code, UnsupportedFeatureError)

    def test_variable_initialization(self):
        code = "int add2(int x) { int a = 2; return x + a; }"
        self.visit_raises(code, UnsupportedFeatureError)

    def test_variable_wrong_expr_assignment(self):
        code = "int add2(int x) { int a; a = 2.5; return a; }"
        self.visit_raises(code, UnsupportedFeatureError)

    def test_wrong_return_type(self):
        code = "int add2(int x) { return 2.5; }"
        self.visit_raises(code, UnsupportedFeatureError)

    def test_valid_sum_function(self):
        code = """
        int sum(int a, int b) {
            return a + b;
        }
        """

        self.visit(code)

    def test_incompatible_type_operands(self):
        code = """
        int compare(int a, float b) {
            return a < b;
        }
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_incompatible_return_type(self):
        code = """
        _Bool is_positive(int a) {
            return a + 1;
        }
        """

        self.visit_raises(code, UnsupportedFeatureError)

        code = """
        void do_nothing() {
            return 42;
        }
        """

        self.visit_raises(code, UnsupportedFeatureError)

    def test_composed_expressions(self):
        code = """
        int complex_operation(int a, int b, int c) {
            return (a + b) * (b - c) / (a % (c + 1));
        }
        """

        visitor = self.visit(code)
        self.assertIn("complex_operation", visitor.functions)
        f = visitor.functions["complex_operation"]
        a = Var("a_0", INT)
        b = Var("b_0", INT)
        c = Var("c_0", INT)
        self.assertEqual(f.vars, {a, b, c})
        self.assertIs(f.return_type, INT)
        self.assertEqual(len(f.instructions), 1)
        self.assertEqual(f.instructions[0], Return(Div(Mul(Add(a, b), Sub(b, c)), Mod(a, Add(c, 1)))))

    def test_bool_complex_expression(self):
        code = """
        _Bool complex_bool(_Bool x, _Bool y, _Bool z) {
            return (x && y) || (!z);
        }
        """

        visitor = self.visit(code)
        self.assertIn("complex_bool", visitor.functions)
        f = visitor.functions["complex_bool"]
        x = Var("x_0", BOOL)
        y = Var("y_0", BOOL)
        z = Var("z_0", BOOL)
        self.assertEqual(f.vars, {x, y, z})
        self.assertIs(f.return_type, BOOL)
        self.assertEqual(len(f.instructions), 1)
        self.assertEqual(f.instructions[0], Return(Or(And(x, y), Not(z))))

    def test_pointer_equality(self):
        code = """
        struct Node {
            int value;
            struct Node* next;
        };

        _Bool are_same_pointers(struct Node* p1, struct Node* p2) {
            return p1 == p2;
        }
        """

        visitor = self.visit(code)
        self.assertIn("are_same_pointers", visitor.functions)
        f = visitor.functions["are_same_pointers"]
        p1 = Var("p1_0", Pointer(visitor.sorts["Node"]))
        p2 = Var("p2_0", Pointer(visitor.sorts["Node"]))
        self.assertEqual(f.vars, {p1, p2})
        self.assertIs(f.return_type, BOOL)
        self.assertEqual(len(f.instructions), 1)
        self.assertEqual(f.instructions[0], Return(PtrIsPtr(p1, p2)))

    def test_pointer_inequality(self):
        code = """
        struct Node {
            int value;
            struct Node* next;
        };
        _Bool are_different_pointers(struct Node* p1, struct Node* p2) {
            return p1 != p2;
        }
        """
        visitor = self.visit(code)
        self.assertIn("are_different_pointers", visitor.functions)
        f = visitor.functions["are_different_pointers"]
        p1 = Var("p1_0", Pointer(visitor.sorts["Node"]))
        p2 = Var("p2_0", Pointer(visitor.sorts["Node"]))
        self.assertEqual(f.vars, {p1, p2})
        self.assertIs(f.return_type, BOOL)
        self.assertEqual(len(f.instructions), 1)
        self.assertEqual(f.instructions[0], Return(Not(PtrIsPtr(p1, p2))))

    def test_pointer_is_nil(self):
        code = """
        struct Node {
            int value;
            struct Node* next;
        };
        _Bool is_nil(struct Node* p) {
            return p;
        }
        """
        visitor = self.visit(code)
        self.assertIn("is_nil", visitor.functions)
        f = visitor.functions["is_nil"]
        p = Var("p_0", Pointer(visitor.sorts["Node"]))
        self.assertEqual(f.vars, {p})
        self.assertIs(f.return_type, BOOL)
        self.assertEqual(len(f.instructions), 1)
        self.assertEqual(f.instructions[0], Return(Not(PtrIsNil(p))))

    def test_pointer_is_not_nil(self):
        code = """
        struct Node {
            int value;
            struct Node* next;
        };
        _Bool is_not_nil(struct Node* p) {
            return !p;
        }
        """
        visitor = self.visit(code)
        self.assertIn("is_not_nil", visitor.functions)
        f = visitor.functions["is_not_nil"]
        p = Var("p_0", Pointer(visitor.sorts["Node"]))
        self.assertEqual(f.vars, {p})
        self.assertIs(f.return_type, BOOL)
        self.assertEqual(len(f.instructions), 1)
        self.assertEqual(f.instructions[0], Return(PtrIsNil(p)))

    def test_if(self):
        code = """
        void max(int a, int b) {
            if (a > b) {
                a = a + b;
            }
        }
        """
        visitor = self.visit(code)
        self.assertIn("max", visitor.functions)
        f = visitor.functions["max"]
        a = Var("a_0", INT)
        b = Var("b_0", INT)
        self.assertEqual(f.vars, {a, b})
        self.assertIs(f.return_type, UNIT)
        self.assertEqual(len(f.instructions), 4)
        self.assertEqual(
            f.instructions,
            (
                IfGoto(Gt(a, b), "#IFTRUE_0"),
                Goto("#ENDIF_0"),
                VarAssignExpr(a, Add(a, b), label="#IFTRUE_0"),
                Skip(label="#ENDIF_0"),
            ),
        )

    def test_if_else(self):
        code = """
        void max(int a, int b) {
            if (a > b) {
                a = a + b;
            } else {
                b = a + b;
            }
        }
        """
        visitor = self.visit(code)
        self.assertIn("max", visitor.functions)
        f = visitor.functions["max"]
        a = Var("a_0", INT)
        b = Var("b_0", INT)
        self.assertEqual(f.vars, {a, b})
        self.assertIs(f.return_type, UNIT)
        self.assertEqual(len(f.instructions), 5)
        self.assertEqual(
            f.instructions,
            (
                IfGoto(Gt(a, b), "#IFTRUE_0"),
                VarAssignExpr(b, Add(a, b)),
                Goto("#ENDIF_0"),
                VarAssignExpr(a, Add(a, b), label="#IFTRUE_0"),
                Skip(label="#ENDIF_0"),
            ),
        )

    def test_while(self):
        code = """
        void countdown() {
            int n;
            n = 10;
            while (n > 0) {
                int x;
                x = 1;
                n = n - 1;
            }
        }
        """
        visitor = self.visit(code)
        self.assertIn("countdown", visitor.functions)
        f = visitor.functions["countdown"]
        n = Var("n_0", INT)
        x = Var("x_0", INT)
        self.assertEqual(f.vars, {n, x})
        self.assertIs(f.return_type, UNIT)
        self.assertEqual(len(f.instructions), 5)
        self.assertEqual(
            f.instructions,
            (
                VarAssignExpr(n, 10),
                Goto("#WHILE_COND_0"),
                VarAssignExpr(x, 1, label="#WHILE_BODY_0"),
                VarAssignExpr(n, Sub(n, 1)),
                IfGoto(Gt(n, 0), "#WHILE_BODY_0", label="#WHILE_COND_0"),
            ),
        )

    def test_nested_goto(self):
        code = """
        void nested_goto(int x) {
            if (x > 0) {
                x = x + 1;
                goto end;
            }
            x = x - 1;
        end:
            return;
        }
        """
        visitor = self.visit(code)
        self.assertIn("nested_goto", visitor.functions)
        f = visitor.functions["nested_goto"]
        x = Var("x_0", INT)
        self.assertEqual(f.vars, {x})
        self.assertIs(f.return_type, UNIT)
        self.assertEqual(len(f.instructions), 7)
        self.assertEqual(
            f.instructions,
            (
                IfGoto(Gt(x, 0), "#IFTRUE_0"),
                Goto("#ENDIF_0"),
                VarAssignExpr(x, Add(x, 1), label="#IFTRUE_0"),
                Goto("end"),
                Skip(label="#ENDIF_0"),
                VarAssignExpr(x, Sub(x, 1)),
                Return(label="end"),
            ),
        )
