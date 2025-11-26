# ruff: noqa: N802
from unittest import TestCase

from ir.enviroment import Enviroment
from ir.expressions import *
from ir.function import Function
from ir.instructions import *
from ir.sorts import INT, UNIT, Pointer, Struct


class FunctionTest(TestCase):
    def test_Function_validation(self):
        node_struct = Struct(
            name="BSTNode",
            fields={Var("value", INT)},
            struct_ptrs={"left", "right"},
        )
        value = Var("value", INT)
        key = Var("key", INT)
        root = Var("root", Pointer(node_struct))
        int_root = Var("int_root", INT)
        int_ptr = Var("int_ptr", Pointer(INT))
        curr = Var("curr", Pointer(node_struct))

        function = Function(
            name="bsearch",
            env=Enviroment(node_struct, root=root, local_vars={key, value, curr}),
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

        # root is not of POINTER sort
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=int_root, local_vars=set()),
                return_type=UNIT,
                instructions=(Return(),),
            )

        # non-node_struct pointer in local_vars
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=root, local_vars={int_ptr}),
                return_type=UNIT,
                instructions=(Return(),),
            )

        # return type is UNIT but Return has a value
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=root, local_vars=set()),
                return_type=UNIT,
                instructions=(Return(1),),
            )

        # return value is an unknown variable
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=root, local_vars=set()),
                return_type=INT,
                instructions=(Return(value),),
            )

        # return value has incorrect sort
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=root, local_vars={value}),
                return_type=REAL,
                instructions=(Return(value),),
            )

        # New instruction with incorrect pointer sort
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=root, local_vars={int_root}),
                return_type=INT,
                instructions=(New(int_root),),
            )

        # Free instruction with incorrect pointer sort
        with self.assertRaises(ValueError):
            Function(
                name="f",
                env=Enviroment(node_struct, root=root, local_vars={int_root}),
                return_type=INT,
                instructions=(Free(int_root),),
            )
