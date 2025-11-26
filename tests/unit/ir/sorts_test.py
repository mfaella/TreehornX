# ruff: noqa: N802
from unittest import TestCase

from ir.expressions import Var
from ir.sorts import *


class TestSorts(TestCase):
    def test_internal_functionalities(self):
        self.assertIs(INT, Int())
        self.assertEqual(INT, Int())

        self.assertIs(BOOL, Enum("bool", ("TRUE", "FALSE")))
        self.assertEqual(BOOL, Enum("bool", ("TRUE", "FALSE")))

        self.assertIs(REAL, Real())
        self.assertEqual(REAL, Real())

    def test_Enum_uniqueness(self):
        self.assertTrue(BOOL is Enum("bool", ("TRUE", "FALSE")))
        self.assertTrue(Enum("color", ("red", "black")) is Enum("color", ("red", "black")))
        self.assertTrue(Enum("fruit", ("apple", "banana", "pear")) is Enum("fruit", ("apple", "banana", "pear")))

    def test_Struct_field_uniqueness_validation(self):
        with self.assertRaises(ValueError):
            Struct(
                name="MyStruct",
                fields={Var("a", INT), Var("b", REAL), Var("a", BOOL)},
            )

        with self.assertRaises(ValueError):
            Struct(
                name="AnotherStruct",
                fields={Var("x", INT), Var("y", REAL)},
                struct_ptrs={"x", "z"},
            )

    def test_Struct_uniqueness(self):
        struct1 = Struct(
            name="UniqueStruct",
            fields={Var("a", INT), Var("b", REAL)},
        )
        struct2 = Struct(
            name="UniqueStruct",
            fields={Var("a", INT), Var("b", REAL)},
        )
        struct3 = Struct(
            name="UniqueStruct",
            fields={Var("a", INT), Var("b", REAL)},
            struct_ptrs={"c"},
        )
        struct4 = Struct(
            name="UniqueStruct",
            fields={Var("a", INT), Var("b", REAL)},
            struct_ptrs={"c"},
        )

        self.assertIs(struct1, struct2)
        self.assertIsNot(struct1, struct3)
        self.assertIs(struct3, struct4)
