# ruff: noqa: N802
from unittest import TestCase

from ir.expressions import Var
from ir.sorts import *


class TestSorts(TestCase):
    def test_natives_uniqueness(self):
        self.assertIs(INT, Int())
        self.assertEqual(INT, Int())

        self.assertIs(REAL, Real())
        self.assertEqual(REAL, Real())

        self.assertIs(UNIT, Unit())
        self.assertEqual(UNIT, Unit())

        self.assertIsNot(INT, REAL)
        self.assertIsNot(INT, UNIT)
        self.assertIsNot(UNIT, REAL)

    def test_Enum_uniqueness(self):
        self.assertIs(BOOL, Enum("bool", {"TRUE": 1, "FALSE": 0}))
        self.assertIsNot(BOOL, Enum("bool", {"TRUE": 0, "FALSE": 1}))
        self.assertIs(Enum("color", {"red": 23, "black": -20}), Enum("color", {"red": 23, "black": -20}))
        self.assertIsNot(Enum("color", {"red": 23, "black": -20}), Enum("color", {"red": -45, "black": 0}))
        self.assertTrue(
            Enum("fruit", {"apple": 0, "banana": 1, "pear": 2}), Enum("fruit", {"apple": 0, "banana": 1, "pear": 2})
        )

    def test_Struct_field_uniqueness_validation(self):
        with self.assertRaises(ValueError):
            Struct(
                name="MyStruct",
                struct_ptrs={"self_pointer"},
                struct_vars={Var("a", INT), Var("b", REAL), Var("a", BOOL)},
            )

        with self.assertRaises(ValueError):
            Struct(
                name="AnotherStruct",
                struct_vars={Var("x", INT), Var("y", REAL)},
                struct_ptrs={"x", "z"},
            )

    def test_Struct_uniqueness(self):
        struct1 = Struct(
            name="UniqueStruct",
            struct_ptrs={"next"},
            struct_vars={Var("a", INT), Var("b", REAL)},
        )
        struct2 = Struct(
            name="UniqueStruct",
            struct_ptrs={"next"},
            struct_vars={Var("a", INT), Var("b", REAL)},
        )
        struct3 = Struct(
            name="UniqueStruct",
            struct_vars={Var("a", INT), Var("b", REAL)},
            struct_ptrs={"left", "right"},
        )
        struct4 = Struct(
            name="UniqueStruct",
            struct_vars={Var("a", INT), Var("b", REAL)},
            struct_ptrs={"left", "right"},
        )

        self.assertIs(struct1, struct2)
        self.assertIs(struct3, struct4)
        self.assertIsNot(struct1, struct3)

    def test_Pointer_uniqueness(self):
        struct1 = Struct(
            name="Node",
            struct_ptrs={"next"},
            struct_vars={Var("value", INT)},
        )

        struct2 = Struct(
            name="Node",
            struct_ptrs={"next"},
            struct_vars={Var("value", REAL)},
        )

        struct3 = Struct(
            name="Node",
            struct_ptrs={"left", "right"},
            struct_vars={Var("value", REAL)},
        )

        ptr1 = Pointer(struct1)
        ptr2 = Pointer(struct1)
        ptr3 = Pointer(struct2)
        ptr4 = Pointer(struct2)
        ptr5 = Pointer(struct3)
        ptr6 = Pointer(struct3)

        self.assertIs(ptr1, ptr2)
        self.assertIs(ptr3, ptr4)
        self.assertIs(ptr5, ptr6)
        self.assertIsNot(ptr1, ptr3)
        self.assertIsNot(ptr1, ptr5)
        self.assertIsNot(ptr3, ptr5)
