from unittest import TestCase

from ir.expressions import (
    FALSE,
    TRUE,
    Add,
    And,
    Div,
    EnumConst,
    Eq,
    Field,
    Ge,
    Gt,
    Le,
    Lt,
    Mod,
    Mul,
    Ne,
    Negate,
    Not,
    Or,
    PtrIsNil,
    PtrIsPtr,
    Sub,
    Var,
    sort_of,
)
from ir.sorts import BOOL, INT, REAL, UNIT, Pointer, Struct


birfc_struct_ptr = Pointer(
    Struct(
        "birfc",
        {
            Var("f", Pointer(INT)),
            Var("i", INT),
            Var("r", REAL),
            Var("b", BOOL),
        },
        {"c"},
    )
)


class TestExpressions(TestCase):
    def test_Var_validation(self):
        self.assertRaises(ValueError, lambda: Var("u", UNIT))

        p = Var("p", Pointer(INT))
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        self.assertIs(sort_of(p), Pointer(INT))
        self.assertIs(sort_of(i), INT)
        self.assertIs(sort_of(r), REAL)
        self.assertIs(sort_of(b), BOOL)
        self.assertRaises(ValueError, lambda: Var("u", UNIT))

    def test_Field_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)

        pf = Field(p, "f")
        pi = Field(p, "i")
        pr = Field(p, "r")
        pb = Field(p, "b")

        self.assertRaises(ValueError, lambda: Field(p, "a"))

        self.assertIs(sort_of(pf), Pointer(INT))
        self.assertIs(sort_of(pi), INT)
        self.assertIs(sort_of(pr), REAL)
        self.assertIs(sort_of(pb), BOOL)

        self.assertRaises(ValueError, lambda: Field(Var("p", Pointer(INT)), "f"))
        self.assertRaises(ValueError, lambda: Field(Var("p", Pointer(REAL)), "f"))
        self.assertRaises(ValueError, lambda: Field(Var("p", Pointer(Pointer(INT))), "f"))
        self.assertRaises(ValueError, lambda: Field(Var("p", Pointer(BOOL)), "f"))
        self.assertRaises(ValueError, lambda: Field(Var("p", Pointer(UNIT)), "f"))

        self.assertRaises(ValueError, lambda: Field(i, "f"))
        self.assertRaises(ValueError, lambda: Field(i, "i"))
        self.assertRaises(ValueError, lambda: Field(r, "f"))
        self.assertRaises(ValueError, lambda: Field(r, "r"))
        self.assertRaises(ValueError, lambda: Field(b, "f"))
        self.assertRaises(ValueError, lambda: Field(b, "b"))

    def test_EnumConst_validation(self):
        self.assertIs(sort_of(TRUE), BOOL)
        self.assertIs(sort_of(FALSE), BOOL)
        self.assertIs(TRUE, EnumConst(BOOL, "TRUE"))
        self.assertIs(FALSE, EnumConst(BOOL, "FALSE"))

        self.assertRaises(ValueError, lambda: EnumConst(BOOL, "MAYBE"))
        self.assertRaises(ValueError, lambda: EnumConst(BOOL, "true"))
        self.assertRaises(ValueError, lambda: EnumConst(BOOL, "false"))

    def test_PtrIsNil_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")
        fp = Field(p, "f")

        self.assertIs(sort_of(PtrIsNil(p)), BOOL)
        self.assertRaises(ValueError, lambda: PtrIsNil(fp))
        self.assertRaises(ValueError, lambda: PtrIsNil(i))
        self.assertRaises(ValueError, lambda: PtrIsNil(r))
        self.assertRaises(ValueError, lambda: PtrIsNil(b))
        self.assertRaises(ValueError, lambda: PtrIsNil(fi))
        self.assertRaises(ValueError, lambda: PtrIsNil(fr))
        self.assertRaises(ValueError, lambda: PtrIsNil(fb))

    def test_PtrIsPtr_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("q", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")
        fp = Field(p, "f")

        self.assertIs(sort_of(PtrIsPtr(p, q)), BOOL)
        self.assertRaises(ValueError, lambda: PtrIsPtr(fp, fp))
        self.assertRaises(ValueError, lambda: PtrIsPtr(fp, i))
        self.assertRaises(ValueError, lambda: PtrIsPtr(r, q))
        self.assertRaises(ValueError, lambda: PtrIsPtr(p, fp))
        self.assertRaises(ValueError, lambda: PtrIsPtr(p, fr))
        self.assertRaises(ValueError, lambda: PtrIsPtr(p, r))
        self.assertRaises(ValueError, lambda: PtrIsPtr(fb, fb))
        self.assertRaises(ValueError, lambda: PtrIsPtr(fi, i))

    def test_And_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("q", birfc_struct_ptr)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        b3 = Var("b3", BOOL)
        b4 = Var("b4", BOOL)
        fb = Field(p, "b")

        self.assertIs(sort_of(And(b1, b2)), BOOL)
        self.assertIs(sort_of(And(PtrIsNil(p), PtrIsPtr(p, q), PtrIsNil(q))), BOOL)

        self.assertRaises(ValueError, lambda: And(p, b2))
        self.assertRaises(ValueError, lambda: And(b1, p))
        self.assertRaises(ValueError, lambda: And(b1, fb))

        self.assertEqual(And(And(b1, b2), And(b3, b4)), And(b1, b2, b3, b4))
        self.assertEqual(And(And(b1, b2), Or(b3, b4)), And(b1, b2, Or(b3, b4)))

    def test_Or_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("q", birfc_struct_ptr)
        i = Var("i", INT)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        b3 = Var("b3", BOOL)
        b4 = Var("b4", BOOL)

        self.assertIs(sort_of(Or(b1, b2)), BOOL)
        self.assertIs(sort_of(Or(PtrIsNil(p), PtrIsPtr(p, q), PtrIsNil(q))), BOOL)
        self.assertRaises(ValueError, lambda: Or(p, b2))
        self.assertRaises(ValueError, lambda: Or(b1, i))

        self.assertEqual(Or(Or(b1, b2), Or(b3, b4)), Or(b1, b2, b3, b4))
        self.assertEqual(Or(Or(b1, b2), And(b3, b4)), Or(b1, b2, And(b3, b4)))

    def test_Not_validation(self):
        p = Var("p", birfc_struct_ptr)
        b = Var("b", BOOL)
        fp = Field(p, "f")

        self.assertIs(sort_of(Not(b)), BOOL)
        self.assertIs(sort_of(Not(PtrIsNil(p))), BOOL)

        self.assertRaises(ValueError, lambda: Not(p))
        self.assertRaises(ValueError, lambda: Not(fp))

    def test_Eq_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("q", Pointer(INT))
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fp = Field(p, "f")
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Eq(i, i)), BOOL)
        self.assertIs(sort_of(Eq(r, r)), BOOL)
        self.assertIs(sort_of(Eq(b, b)), BOOL)

        self.assertRaises(ValueError, lambda: Eq(i, fi))
        self.assertRaises(ValueError, lambda: Eq(r, fr))
        self.assertRaises(ValueError, lambda: Eq(b, fb))
        self.assertRaises(ValueError, lambda: Eq(p, q))
        self.assertRaises(ValueError, lambda: Eq(fp, fp))
        self.assertRaises(ValueError, lambda: Eq(p, i))
        self.assertRaises(ValueError, lambda: Eq(p, fi))
        self.assertRaises(ValueError, lambda: Eq(i, r))
        self.assertRaises(ValueError, lambda: Eq(r, b))
        self.assertRaises(ValueError, lambda: Eq(b, fp))
        self.assertRaises(ValueError, lambda: Eq(fp, p))

    def test_Ne_validation(self):
        p = Var("p", birfc_struct_ptr)
        q = Var("q", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fp = Field(p, "f")
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Ne(i, i)), BOOL)
        self.assertIs(sort_of(Ne(r, r)), BOOL)
        self.assertIs(sort_of(Ne(b, b)), BOOL)

        self.assertRaises(ValueError, lambda: Ne(i, fi))
        self.assertRaises(ValueError, lambda: Ne(r, fr))
        self.assertRaises(ValueError, lambda: Ne(b, fb))
        self.assertRaises(ValueError, lambda: Ne(p, q))
        self.assertRaises(ValueError, lambda: Ne(fp, fp))
        self.assertRaises(ValueError, lambda: Ne(p, i))
        self.assertRaises(ValueError, lambda: Ne(p, fi))
        self.assertRaises(ValueError, lambda: Ne(i, r))
        self.assertRaises(ValueError, lambda: Ne(r, b))
        self.assertRaises(ValueError, lambda: Ne(b, fp))
        self.assertRaises(ValueError, lambda: Ne(fp, p))

    def test_Le_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Le(i, i)), BOOL)
        self.assertIs(sort_of(Le(r, r)), BOOL)
        self.assertIs(sort_of(Le(0, Add(i, 1))), BOOL)

        self.assertRaises(ValueError, lambda: Le(i, fi))
        self.assertRaises(ValueError, lambda: Le(r, fr))
        self.assertRaises(ValueError, lambda: Le(p, p))
        self.assertRaises(ValueError, lambda: Le(p, i))
        self.assertRaises(ValueError, lambda: Le(p, fi))
        self.assertRaises(ValueError, lambda: Le(i, r))
        self.assertRaises(ValueError, lambda: Le(r, b))
        self.assertRaises(ValueError, lambda: Le(b, b))
        self.assertRaises(ValueError, lambda: Le(b, fb))

    def test_Lt_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Lt(i, i)), BOOL)
        self.assertIs(sort_of(Lt(r, r)), BOOL)
        self.assertIs(sort_of(Lt(0, Sub(i, 1))), BOOL)

        self.assertRaises(ValueError, lambda: Lt(i, fi))
        self.assertRaises(ValueError, lambda: Lt(r, fr))
        self.assertRaises(ValueError, lambda: Lt(p, p))
        self.assertRaises(ValueError, lambda: Lt(p, i))
        self.assertRaises(ValueError, lambda: Lt(p, fi))
        self.assertRaises(ValueError, lambda: Lt(i, r))
        self.assertRaises(ValueError, lambda: Lt(r, b))
        self.assertRaises(ValueError, lambda: Lt(b, b))
        self.assertRaises(ValueError, lambda: Lt(b, fb))

    def test_Gt_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Gt(i, i)), BOOL)
        self.assertIs(sort_of(Gt(r, r)), BOOL)
        self.assertIs(sort_of(Gt(0, Add(i, 1))), BOOL)

        self.assertRaises(ValueError, lambda: Gt(i, fi))
        self.assertRaises(ValueError, lambda: Gt(r, fr))
        self.assertRaises(ValueError, lambda: Gt(p, p))
        self.assertRaises(ValueError, lambda: Gt(p, i))
        self.assertRaises(ValueError, lambda: Gt(p, fi))
        self.assertRaises(ValueError, lambda: Gt(i, r))
        self.assertRaises(ValueError, lambda: Gt(r, b))
        self.assertRaises(ValueError, lambda: Gt(b, b))
        self.assertRaises(ValueError, lambda: Gt(b, fb))

    def test_Ge_validation(self):
        p = Var("p", birfc_struct_ptr)
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Ge(i, i)), BOOL)
        self.assertIs(sort_of(Ge(r, r)), BOOL)
        self.assertIs(sort_of(Ge(0, Sub(i, 1))), BOOL)

        self.assertRaises(ValueError, lambda: Ge(i, fi))
        self.assertRaises(ValueError, lambda: Ge(r, fr))
        self.assertRaises(ValueError, lambda: Ge(p, p))
        self.assertRaises(ValueError, lambda: Ge(p, i))
        self.assertRaises(ValueError, lambda: Ge(p, fi))
        self.assertRaises(ValueError, lambda: Ge(i, r))
        self.assertRaises(ValueError, lambda: Ge(r, b))
        self.assertRaises(ValueError, lambda: Ge(b, b))
        self.assertRaises(ValueError, lambda: Ge(b, fb))

    def test_Add_validation(self):
        i1 = Var("i1", INT)
        i2 = Var("i2", INT)
        r1 = Var("r1", REAL)
        r2 = Var("r2", REAL)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        p = Var("p", birfc_struct_ptr)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Add(i1, i2)), INT)
        self.assertIs(sort_of(Add(r1, r2)), REAL)

        self.assertRaises(ValueError, lambda: Add(i1, fi))
        self.assertRaises(ValueError, lambda: Add(i2, fi))
        self.assertRaises(ValueError, lambda: Add(r1, fr))
        self.assertRaises(ValueError, lambda: Add(fr, r2))

        self.assertRaises(ValueError, lambda: Add(i1, r1))
        self.assertRaises(ValueError, lambda: Add(i1, p))
        self.assertRaises(ValueError, lambda: Add(p, p))
        self.assertRaises(ValueError, lambda: Add(b1, b2))
        self.assertRaises(ValueError, lambda: Add(i1, fb))
        self.assertRaises(ValueError, lambda: Add(r1, fi))

        self.assertRaises(ValueError, lambda: Add(Add(i1, i2), Add(fi, 3), 5))
        self.assertRaises(ValueError, lambda: Add(Add(r1, r2), Sub(fr, 2.0), 4.0))

        self.assertEqual(Add(Add(i1, i2), Add(i2, 3), 5), Add(i1, i2, i2, 3, 5))
        self.assertEqual(Add(Add(r1, r2), Sub(r1, 2.0), 4.0), Add(r1, r2, Sub(r1, 2.0), 4.0))

    def test_Sub_validation(self):
        i1 = Var("i1", INT)
        i2 = Var("i2", INT)
        r1 = Var("r1", REAL)
        r2 = Var("r2", REAL)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        p = Var("p", birfc_struct_ptr)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Sub(i1, i2)), INT)
        self.assertIs(sort_of(Sub(r1, r2)), REAL)

        self.assertRaises(ValueError, lambda: Sub(i1, fi))
        self.assertRaises(ValueError, lambda: Sub(r1, fr))
        self.assertRaises(ValueError, lambda: Sub(i1, r1))
        self.assertRaises(ValueError, lambda: Sub(i1, p))
        self.assertRaises(ValueError, lambda: Sub(p, p))
        self.assertRaises(ValueError, lambda: Sub(b1, b2))
        self.assertRaises(ValueError, lambda: Sub(i1, fb))
        self.assertRaises(ValueError, lambda: Sub(r1, fi))

    def test_Mul_validation(self):
        i1 = Var("i1", INT)
        i2 = Var("i2", INT)
        r1 = Var("r1", REAL)
        r2 = Var("r2", REAL)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        p = Var("p", birfc_struct_ptr)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Mul(i1, i2)), INT)
        self.assertIs(sort_of(Mul(r1, r2)), REAL)

        self.assertRaises(ValueError, lambda: Mul(i1, fi))
        self.assertRaises(ValueError, lambda: Mul(r1, fr))
        self.assertRaises(ValueError, lambda: Mul(i1, r1))
        self.assertRaises(ValueError, lambda: Mul(i1, p))
        self.assertRaises(ValueError, lambda: Mul(p, p))
        self.assertRaises(ValueError, lambda: Mul(b1, b2))
        self.assertRaises(ValueError, lambda: Mul(i1, fb))
        self.assertRaises(ValueError, lambda: Mul(r1, fi))

        self.assertRaises(ValueError, lambda: Mul(Mul(i1, i2), Mul(fi, 3), 5))
        self.assertRaises(ValueError, lambda: Mul(Mul(r1, r2), Div(fr, 2.0), 4.0))

        self.assertEqual(Mul(Mul(i1, i2), Mul(i1, 3), 5), Mul(i1, i2, i1, 3, 5))
        self.assertEqual(Mul(Mul(r1, r2), Div(r2, 2.0), 4.0), Mul(r1, r2, Div(r2, 2.0), 4.0))

    def test_Div_validation(self):
        i1 = Var("i1", INT)
        i2 = Var("i2", INT)
        r1 = Var("r1", REAL)
        r2 = Var("r2", REAL)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        p = Var("p", birfc_struct_ptr)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Div(i1, i2)), INT)
        self.assertIs(sort_of(Div(r1, r2)), REAL)

        self.assertRaises(ValueError, lambda: Div(i1, fi))
        self.assertRaises(ValueError, lambda: Div(r1, fr))

        self.assertRaises(ValueError, lambda: Div(i1, r1))
        self.assertRaises(ValueError, lambda: Div(i1, p))
        self.assertRaises(ValueError, lambda: Div(p, p))
        self.assertRaises(ValueError, lambda: Div(b1, b2))
        self.assertRaises(ValueError, lambda: Div(i1, fb))
        self.assertRaises(ValueError, lambda: Div(r1, fi))

    def test_Mod_validation(self):
        i1 = Var("i1", INT)
        i2 = Var("i2", INT)
        r1 = Var("r1", REAL)
        r2 = Var("r2", REAL)
        b1 = Var("b1", BOOL)
        b2 = Var("b2", BOOL)
        p = Var("p", birfc_struct_ptr)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Mod(i1, i2)), INT)

        self.assertRaises(ValueError, lambda: Mod(i1, fi))
        self.assertRaises(ValueError, lambda: Mod(r1, r2))
        self.assertRaises(ValueError, lambda: Mod(r1, fr))
        self.assertRaises(ValueError, lambda: Mod(i1, r1))
        self.assertRaises(ValueError, lambda: Mod(i1, p))
        self.assertRaises(ValueError, lambda: Mod(p, p))
        self.assertRaises(ValueError, lambda: Mod(b1, b2))
        self.assertRaises(ValueError, lambda: Mod(i1, fb))
        self.assertRaises(ValueError, lambda: Mod(r1, fi))

    def test_Negate_validation(self):
        i = Var("i", INT)
        r = Var("r", REAL)
        b = Var("b", BOOL)
        p = Var("p", birfc_struct_ptr)
        fi = Field(p, "i")
        fr = Field(p, "r")
        fb = Field(p, "b")

        self.assertIs(sort_of(Negate(i)), INT)
        self.assertIs(sort_of(Negate(r)), REAL)
        self.assertRaises(ValueError, lambda: Negate(fi))
        self.assertRaises(ValueError, lambda: Negate(fr))

        self.assertRaises(ValueError, lambda: Negate(b))
        self.assertRaises(ValueError, lambda: Negate(p))
        self.assertRaises(ValueError, lambda: Negate(fb))
