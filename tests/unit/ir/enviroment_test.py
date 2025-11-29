# ruff: noqa: N802
from unittest import TestCase

from ir.enviroment import Enviroment
from ir.expressions import Var
from ir.sorts import INT, REAL, Pointer, Struct


class TestEnviroment(TestCase):
    def test_Enviroment_validation(self):
        node_struct = Struct("BSTNode", {"left", "right"}, {Var("value", INT)})

        # Valid environments

        Enviroment(
            node_struct,
            root=Var("root", Pointer(node_struct)),
            local_vars={
                Var("param1", INT),
                Var("param2", Pointer(node_struct)),
                Var("local1", INT),
                Var("local2", Pointer(node_struct)),
            },
        )

        Enviroment(
            node_struct,
            root=Var("root", Pointer(node_struct)),
            local_vars={
                Var("n", INT),
                Var("q", Pointer(node_struct)),
                Var("local1", INT),
                Var("local2", Pointer(node_struct)),
            },
        )

        # Invalid environment: vairable name duplication
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("n", INT),
                    Var("q", Pointer(node_struct)),
                    Var("n", REAL),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: parameter conflicts with parameter name
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("n", INT),
                    Var("q", Pointer(node_struct)),
                    Var("n", REAL),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: root name conflicts with local variable name
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("param1", INT),
                    Var("param2", Pointer(node_struct)),
                    Var("root", INT),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: root name conflicts with local variable name of a different type
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("param1", INT),
                    Var("param2", Pointer(node_struct)),
                    Var("local1", INT),
                    Var("root", Pointer(node_struct)),
                },
            )

        # Invalid environment: root name conflicts with parameter name
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("root", INT),
                    Var("param2", Pointer(node_struct)),
                    Var("local1", INT),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: root name conflicts with parameter name of a different type
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("param1", INT),
                    Var("root", Pointer(node_struct)),
                    Var("local1", INT),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: duplicate variable names in local_vars
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("m", INT),
                    Var("p", Pointer(node_struct)),
                    Var("a", INT),
                    Var("a", Pointer(node_struct)),
                },
            )

        # Invalid environment: duplicate variable names
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={
                    Var("a", INT),
                    Var("a", Pointer(node_struct)),
                    Var("m", INT),
                    Var("p", Pointer(node_struct)),
                },
            )

        # Invalid environment: root sort is not pointer
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", INT),
                local_vars={
                    Var("param1", INT),
                    Var("param2", Pointer(node_struct)),
                    Var("local1", INT),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: root sort is not struct pointer
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(INT)),
                local_vars={
                    Var("param1", INT),
                    Var("param2", Pointer(node_struct)),
                    Var("local1", INT),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: root sort is not struct pointer of the node struct
        with self.assertRaises(ValueError):
            list_node_struct = Struct("ListNode", {"next"}, {Var("value", INT)})
            Enviroment(
                node_struct,
                root=Var("root", Pointer(list_node_struct)),
                local_vars={
                    Var("param1", INT),
                    Var("param2", Pointer(node_struct)),
                    Var("local1", INT),
                    Var("local2", Pointer(node_struct)),
                },
            )

        # Invalid environment: integer pointer in local_vars
        with self.assertRaises(ValueError):
            Enviroment(
                node_struct,
                root=Var("root", Pointer(node_struct)),
                local_vars={Var("p", Pointer(INT))},
            )
