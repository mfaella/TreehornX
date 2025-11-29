from unittest import TestCase

from ir.expressions import Add, And, Eq, Field, Not, PtrIsNil, Sub, Var
from ir.instructions import (
    FieldAssignExpr,
    FieldAssignNil,
    FieldAssignPtr,
    Free,
    IfGoto,
    New,
    PtrAssignField,
    PtrAssignNil,
    PtrAssignPtr,
    VarAssignExpr,
)
from ir.sorts import BOOL, INT, REAL, Pointer, Struct

birfc_struct_ptr = Pointer(
    Struct(
        "birfc",
        {"c"},
        {
            Var("i", INT),
            Var("r", REAL),
            Var("b", BOOL),
        },
    )
)


class TestInstructions(TestCase):
    def test_IfGoto_validation(self):
        i = Var("i", INT)
        p = Var("p", birfc_struct_ptr)
        condition = And(Eq(i, 0), PtrIsNil(p))

        IfGoto(condition, "label1")
        IfGoto(condition, "label2")

        self.assertRaises(ValueError, lambda: IfGoto(i, "label1"))
        self.assertRaises(ValueError, lambda: IfGoto(Add(i, 1), "label2"))

    def test_PtrAssignNil_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        PtrAssignNil(p)

        self.assertRaises(ValueError, lambda: PtrAssignNil(i))
        self.assertRaises(ValueError, lambda: PtrAssignNil(r))
        self.assertRaises(ValueError, lambda: PtrAssignNil(b))

    def test_PtrAssignPtr_validation(self):
        p = Var("p", birfc_struct_ptr)
        p2 = Var("p2", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        PtrAssignPtr(p, p2)

        self.assertRaises(ValueError, lambda: PtrAssignPtr(p, i))
        self.assertRaises(ValueError, lambda: PtrAssignPtr(p, r))
        self.assertRaises(ValueError, lambda: PtrAssignPtr(p, b))
        self.assertRaises(ValueError, lambda: PtrAssignPtr(i, p))
        self.assertRaises(ValueError, lambda: PtrAssignPtr(r, p))
        self.assertRaises(ValueError, lambda: PtrAssignPtr(b, p))

    def test_PtrAssignField_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")
        fc = Field(p, "c")

        PtrAssignField(p, fc)

        self.assertRaises(ValueError, lambda: PtrAssignField(p, fi))
        self.assertRaises(ValueError, lambda: PtrAssignField(p, fr))
        self.assertRaises(ValueError, lambda: PtrAssignField(p, fb))

    def test_FieldAssignNil_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("p", birfc_struct_ptr)
        qc = Field(q, "c")
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        FieldAssignNil(qc)

        self.assertRaises(ValueError, lambda: FieldAssignNil(fi))
        self.assertRaises(ValueError, lambda: FieldAssignNil(fr))
        self.assertRaises(ValueError, lambda: FieldAssignNil(fb))

    def test_FieldAssignPtr_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("p", birfc_struct_ptr)
        qc = Field(q, "c")
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        FieldAssignPtr(qc, p)

        self.assertRaises(ValueError, lambda: FieldAssignPtr(fi, i))
        self.assertRaises(ValueError, lambda: FieldAssignPtr(fr, r))
        self.assertRaises(ValueError, lambda: FieldAssignPtr(fb, b))

    def test_VarAssignExpr_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        VarAssignExpr(i, i)
        VarAssignExpr(i, Add(i, 1))
        VarAssignExpr(i, Field(p, "i"))
        VarAssignExpr(r, r)
        VarAssignExpr(r, Sub(r, 1.0))
        VarAssignExpr(r, Field(p, "r"))
        VarAssignExpr(b, b)
        VarAssignExpr(b, Field(p, "b"))
        VarAssignExpr(b, Not(b))
        VarAssignExpr(b, Eq(i, 0))

        self.assertRaises(ValueError, lambda: VarAssignExpr(p, p))
        self.assertRaises(ValueError, lambda: VarAssignExpr(i, r))
        self.assertRaises(ValueError, lambda: VarAssignExpr(i, b))
        self.assertRaises(ValueError, lambda: VarAssignExpr(i, Field(p, "c")))
        self.assertRaises(ValueError, lambda: VarAssignExpr(r, b))
        self.assertRaises(ValueError, lambda: VarAssignExpr(r, i))
        self.assertRaises(ValueError, lambda: VarAssignExpr(r, Field(p, "b")))
        self.assertRaises(ValueError, lambda: VarAssignExpr(b, i))
        self.assertRaises(ValueError, lambda: VarAssignExpr(b, r))
        self.assertRaises(ValueError, lambda: VarAssignExpr(b, Field(p, "i")))

    def test_FieldAssignExpr_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("q", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        pi = Field(p, "i")
        pr = Field(p, "r")
        pb = Field(p, "b")

        qi = Field(q, "i")
        qr = Field(q, "r")
        qb = Field(q, "b")

        FieldAssignExpr(pi, i)
        FieldAssignExpr(pi, Add(i, 1))
        FieldAssignExpr(pr, r)
        FieldAssignExpr(pr, Add(r, 1.0))
        FieldAssignExpr(pb, b)
        FieldAssignExpr(pb, Not(b))

        self.assertRaises(ValueError, lambda: FieldAssignExpr(pi, qi))
        self.assertRaises(ValueError, lambda: FieldAssignExpr(pr, qr))
        self.assertRaises(ValueError, lambda: FieldAssignExpr(pb, qb))
        self.assertRaises(ValueError, lambda: FieldAssignExpr(pi, r))
        self.assertRaises(ValueError, lambda: FieldAssignExpr(pr, b))
        self.assertRaises(ValueError, lambda: FieldAssignExpr(pb, i))

    def test_New_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        New(p)

        self.assertRaises(ValueError, lambda: New(i))
        self.assertRaises(ValueError, lambda: New(r))
        self.assertRaises(ValueError, lambda: New(b))

    def test_Free_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        Free(p)

        self.assertRaises(ValueError, lambda: Free(i))
        self.assertRaises(ValueError, lambda: Free(r))
        self.assertRaises(ValueError, lambda: Free(b))
