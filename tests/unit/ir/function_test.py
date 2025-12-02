from unittest import TestCase

from ir.errors import IncompatibleReturnTypeError
from ir.expressions import *
from ir.function import Function
from ir.instructions import *
from ir.sorts import INT, REAL, UNIT, Pointer, Struct

outsider_struct = Struct(name="Outsider", struct_vars={Var("data", INT)}, struct_ptrs={"outsider_next"})


class TestFunction(TestCase):
    def test_Function_validation(self):
        node_struct = Struct(
            name="BSTNode",
            struct_vars={Var("value", INT)},
            struct_ptrs={"left", "right"},
        )
        value = Var("value", INT)
        key = Var("key", INT)
        root = Var("root", Pointer(node_struct))
        int_root = Var("int_root", INT)
        outsider_object = Var("outsider_object", outsider_struct)
        ousider_ptr = Var("outsider_ptr", Pointer(outsider_struct))
        curr = Var("curr", Pointer(node_struct))

        function = Function(
            name="bsearch",
            vars={key, value, curr, root},
            return_type=UNIT,
            instructions=(
                PtrAssignPtr(curr, root),
                IfGoto(And(Not(PtrIsNil(curr)), Ne(key, value)), "loop", label="condition"),
                Goto("end"),
                IfGoto(Lt(key, value), "left_branch", label="loop"),
                PtrAssignField(curr, Field(curr, "right")),
                Goto("condition"),
                PtrAssignField(curr, Field(curr, "left"), label="left_branch"),
                Goto("condition"),
                Return(label="end"),
            ),
        )

        self.assertEqual(function.info_at(0), InstructionInfo(pc=0, next_pc=1))
        self.assertEqual(function.info_at(1), InstructionInfo(pc=1, next_pc=(3, 2)))
        self.assertEqual(function.info_at(2), InstructionInfo(pc=2, next_pc=8))
        self.assertEqual(function.info_at(3), InstructionInfo(pc=3, next_pc=(6, 4)))
        self.assertEqual(function.info_at(4), InstructionInfo(pc=4, next_pc=5))
        self.assertEqual(function.info_at(5), InstructionInfo(pc=5, next_pc=1))
        self.assertEqual(function.info_at(6), InstructionInfo(pc=6, next_pc=7))
        self.assertEqual(function.info_at(7), InstructionInfo(pc=7, next_pc=1))
        self.assertEqual(function.info_at(8), InstructionInfo(pc=8, next_pc=9))

    def test_return_type_unit_with_value_raises(self):
        # return type is UNIT but Return has a value
        with self.assertRaises(IncompatibleReturnTypeError):
            Function(
                name="f",
                vars=set(),
                return_type=UNIT,
                instructions=(Return(1),),
            )

    def test_return_value_unknown_variable_raises(self):
        # return value is an unknown variable
        value = Var("value", INT)
        with self.assertRaises(ValueError):
            Function(
                name="f",
                vars=set(),
                return_type=INT,
                instructions=(Return(value),),
            )

    def test_return_value_incorrect_sort_raises(self):
        # return value has incorrect sort
        value = Var("value", INT)
        with self.assertRaises(IncompatibleReturnTypeError):
            Function(
                name="f",
                vars={value},
                return_type=REAL,
                instructions=(Return(value),),
            )

    def test_new_instruction_incorrect_pointer_sort_raises(self):
        # New instruction with incorrect pointer sort
        int_root = Var("int_root", INT)
        with self.assertRaises(ValueError):
            Function(
                name="f",
                vars={int_root},
                return_type=INT,
                instructions=(New(int_root),),
            )

    def test_free_instruction_incorrect_pointer_sort_raises(self):
        # Free instruction with incorrect pointer sort
        int_root = Var("int_root", INT)
        with self.assertRaises(ValueError):
            Function(
                name="f",
                vars={int_root},
                return_type=INT,
                instructions=(Free(int_root),),
            )
