from unittest import TestCase

from ir.sorts import BOOL, INT, REAL, UNIT, Sort, Struct
from parser._internal.cparser.ScopeStack import ScopeStack


class ScopeStackTest(TestCase):
    def test_scope_stack_initialization(self):
        scopes = ScopeStack()
        self.assertRaises(RuntimeError, scopes.pop_scope)

    def test_push_and_pop_scope(self):
        scopes = ScopeStack()
        scopes.push_scope()
        scopes.push_scope()
        scopes.pop_scope()
        scopes.pop_scope()
        self.assertRaises(RuntimeError, scopes.pop_scope)

    def test_declare_and_get_variable(self):
        scopes = ScopeStack()
        scopes.push_scope()
        scopes.declare_variable("x", INT)
        int_x = scopes.get_variable("x")
        self.assertEqual(int_x.name, "x_0")
        self.assertEqual(int_x.sort, INT)
        scopes.push_scope()
        scopes.declare_variable("x", REAL)
        real_x = scopes.get_variable("x")
        self.assertEqual(real_x.name, "x_1")
        self.assertEqual(real_x.sort, REAL)
        scopes.pop_scope()
        int_x = scopes.get_variable("x")
        self.assertEqual(int_x.name, "x_0")
        self.assertEqual(int_x.sort, INT)
        scopes.push_scope()
        scopes.declare_variable("x", BOOL)
        bool_x = scopes.get_variable("x")
        self.assertEqual(bool_x.name, "x_2")
        self.assertEqual(bool_x.sort, BOOL)

        self.assertIn(bool_x, scopes.vars)
        self.assertIn(int_x, scopes.vars)
        self.assertIn(real_x, scopes.vars)

    def test_get_undeclared_variable(self):
        scopes = ScopeStack()
        scopes.push_scope()
        self.assertRaises(KeyError, lambda: scopes.get_variable("y"))
        scopes.declare_variable("y", REAL)
        scopes.push_scope()
        self.assertRaises(KeyError, lambda: scopes.get_variable("z"))

    def test_redeclare_variable_in_same_scope(self):
        scopes = ScopeStack()
        scopes.push_scope()
        scopes.declare_variable("a", INT)
        self.assertRaises(KeyError, lambda: scopes.declare_variable("a", REAL))
