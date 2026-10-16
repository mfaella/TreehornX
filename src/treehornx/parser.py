"""Parse the C subset with pycparser and lower it to :mod:`treeprog.ir`.

Accepted program shape::

    struct NODE { <fields> };          // int / bool / struct NODE * fields
    void f(struct NODE *root) {        // exactly one parameter: the root
        <declarations>                 // all at the top, no nesting
        <statements>
    }

Statements (each one maps to at most one IR heap statement)::

    p = NULL;   p = q;   p = q->pf;   p = malloc(sizeof(struct NODE));
    p->pf = NULL;   p->pf = q;
    p->df = x;  p->df = 5;  p->df = true;        // variable or constant only
    x = p->df;                                   // nothing else on the rhs
    x = <data expression>;  x += e;  x++;        // data variables/constants only
    b = (p == q);  b = (p != NULL);              // heap condition into a bool
    free(p);
    if / else, while, do-while, for, break, continue, goto/labels, return;

Conditions of if/while/for may combine, with && || !, atomic pointer
conditions (p == q, p != NULL, p) and Boolean data expressions; they are
compiled to ``IfGoto`` chains.  Field accesses are never allowed inside a
condition or an expression: load them into a variable first.

Semantics of uninitialised variables follow the paper: data variables are
non-deterministic (they model inputs), pointer variables are nil.  An
initialiser ``int x = e;`` is lowered to an assignment statement.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from pycparser import c_ast, c_parser

from . import ir
from .ir import DataType

__all__ = ["SubsetError", "parse_program", "parse_file"]

_PREAMBLE = "typedef _Bool bool; "   # kept on line 1 so line numbers match
_ARITH = {"+", "-", "*", "/", "%"}
_ORDER = {"<", "<=", ">", ">="}
_EQ = {"==", "!="}
_LOGIC = {"&&", "||"}
_COMPOUND = {"+=": "+", "-=": "-", "*=": "*", "/=": "/", "%=": "%"}


class SubsetError(Exception):
    """Raised when the input is valid C but outside the accepted subset."""

    def __init__(self, msg: str, node: Optional[c_ast.Node] = None):
        coord = getattr(node, "coord", None)
        if coord is not None and coord.line:
            msg = f"{coord.file}:{coord.line}:{coord.column}: {msg}"
        super().__init__(msg)


def _strip_preprocessor_and_comments(src: str) -> str:
    """Remove comments and ``#`` lines, preserving line numbers."""
    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    src = re.sub(r"/\*.*?\*/", blank, src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r"^[ \t]*#[^\n]*", "", src, flags=re.M)
    return src


def parse_file(path: str) -> ir.Function:
    with open(path, encoding="utf-8") as fh:
        return parse_program(fh.read(), filename=path)


def parse_program(source: str, filename: str = "<input>") -> ir.Function:
    text = _PREAMBLE + _strip_preprocessor_and_comments(source)
    try:
        ast = c_parser.CParser().parse(text, filename)
    except c_parser.ParseError as e:
        raise SubsetError(f"C syntax error: {e}") from None
    return _Lowering(ast).run()


class _Label:
    __slots__ = ("pc", "name")

    def __init__(self, name: Optional[str] = None):
        self.pc: Optional[int] = None
        self.name = name


class _Lowering:
    def __init__(self, ast: c_ast.FileAST):
        self.ast = ast
        self.struct_name = ""
        self.data_fields: Dict[str, ir.DataField] = {}
        self.ptr_fields: Dict[str, ir.PointerField] = {}
        self.ptr_vars: Dict[str, int] = {}
        self.data_vars: Dict[str, Tuple[int, DataType]] = {}
        self.code: List[ir.Stmt] = []
        self.labels: List[_Label] = []
        self.named_labels: Dict[str, _Label] = {}
        self.loops: List[Tuple[_Label, _Label]] = []   # (break, continue)

    # ------------------------------------------------------------------ top
    def run(self) -> ir.Function:
        ext = [e for e in self.ast.ext
               if not (isinstance(e, c_ast.Typedef) and e.name == "bool")]
        if len(ext) != 2:
            raise SubsetError(
                "program must contain exactly one struct declaration "
                "followed by exactly one function definition")
        sdecl, fdef = ext
        self._struct(sdecl)
        if not isinstance(fdef, c_ast.FuncDef):
            raise SubsetError("expected a function definition after the struct", fdef)
        name = self._signature(fdef)
        self._body(fdef.body)
        stmts = self._finish()

        node = ir.NodeStruct(
            self.struct_name,
            tuple(sorted(self.data_fields.values(), key=lambda f: f.id)),
            tuple(sorted(self.ptr_fields.values(), key=lambda f: f.id)))
        pvars = tuple(ir.PointerVariable(i, n) for n, i in
                      sorted(self.ptr_vars.items(), key=lambda kv: kv[1]))
        dvars = tuple(ir.DataVariable(i, n, t) for n, (i, t) in
                      sorted(self.data_vars.items(), key=lambda kv: kv[1][0]))
        return ir.Function(name, node, pvars, dvars, tuple(stmts))

    # ------------------------------------------------------------- types
    def _classify(self, t: c_ast.Node, what: str):
        """Return DataType, or the string 'ptr' for ``struct NODE *``."""
        if isinstance(t, c_ast.TypeDecl) and isinstance(t.type, c_ast.IdentifierType):
            names = t.type.names
            if names == ["int"]:
                return DataType.INT
            if names in (["bool"], ["_Bool"]):
                return DataType.BOOL
            raise SubsetError(f"{what}: unsupported type '{' '.join(names)}' "
                              "(only int, bool and struct pointers)", t)
        if (isinstance(t, c_ast.PtrDecl) and isinstance(t.type, c_ast.TypeDecl)
                and isinstance(t.type.type, c_ast.Struct)):
            sname = t.type.type.name
            if self.struct_name and sname != self.struct_name:
                raise SubsetError(f"{what}: pointer to 'struct {sname}', expected "
                                  f"'struct {self.struct_name}'", t)
            return "ptr"
        raise SubsetError(f"{what}: unsupported type (only int, bool and "
                          "struct pointers)", t)

    def _struct(self, decl: c_ast.Node) -> None:
        if not (isinstance(decl, c_ast.Decl) and decl.name is None
                and isinstance(decl.type, c_ast.Struct) and decl.type.decls):
            raise SubsetError("the program must start with 'struct NAME { ... };'", decl)
        st = decl.type
        self.struct_name = st.name
        if not st.name:
            raise SubsetError("the node struct must be named", decl)
        for f in st.decls:
            if f.name in self.data_fields or f.name in self.ptr_fields:
                raise SubsetError(f"duplicate field '{f.name}'", f)
            kind = self._classify(f.type, f"field '{f.name}'")
            if kind == "ptr":
                self.ptr_fields[f.name] = ir.PointerField(len(self.ptr_fields), f.name)
            else:
                self.data_fields[f.name] = ir.DataField(len(self.data_fields), f.name, kind)
        if not self.ptr_fields:
            raise SubsetError(f"struct {self.struct_name} has no pointer fields", decl)

    def _signature(self, fdef: c_ast.FuncDef) -> str:
        fdecl = fdef.decl.type
        ret = fdecl.type
        if not (isinstance(ret, c_ast.TypeDecl) and isinstance(ret.type, c_ast.IdentifierType)
                and ret.type.names == ["void"]):
            raise SubsetError("the function must return void", fdef.decl)
        params = fdecl.args.params if fdecl.args else []
        if len(params) != 1 or not isinstance(params[0], c_ast.Decl):
            raise SubsetError("the function must take exactly one parameter, the root "
                              f"'struct {self.struct_name} *'", fdef.decl)
        p = params[0]
        if self._classify(p.type, f"parameter '{p.name}'") != "ptr":
            raise SubsetError(f"the parameter must be 'struct {self.struct_name} *'", p)
        self.ptr_vars[p.name] = 0
        return fdef.decl.name

    def _body(self, body: c_ast.Compound) -> None:
        items = body.block_items or []
        inits: List[Tuple[c_ast.Node, c_ast.Node]] = []
        i = 0
        while i < len(items) and isinstance(items[i], c_ast.Decl):
            d = items[i]
            if d.name in self.ptr_vars or d.name in self.data_vars:
                raise SubsetError(f"redeclaration of '{d.name}'", d)
            if d.name in ("NULL", "true", "false", "malloc", "free"):
                raise SubsetError(f"'{d.name}' is reserved", d)
            kind = self._classify(d.type, f"variable '{d.name}'")
            if kind == "ptr":
                self.ptr_vars[d.name] = len(self.ptr_vars)
            else:
                self.data_vars[d.name] = (len(self.data_vars), kind)
            if d.init is not None:
                inits.append((c_ast.ID(d.name, coord=d.coord), d.init))
            i += 1
        for lhs, rhs in inits:
            self._assign(lhs, rhs, lhs)
        for s in items[i:]:
            self._stmt(s)

    # --------------------------------------------------------- emission
    def _emit(self, s: ir.Stmt) -> None:
        self.code.append(s)

    def _new_label(self, name: Optional[str] = None) -> _Label:
        lab = _Label(name)
        self.labels.append(lab)
        return lab

    def _place(self, lab: _Label) -> None:
        lab.pc = len(self.code)

    def _finish(self) -> List[ir.Stmt]:
        for name, lab in self.named_labels.items():
            if lab.pc is None:
                raise SubsetError(f"goto to undefined label '{name}'")
        end = len(self.code)
        if not self.code or not isinstance(self.code[-1], ir.Exit) or \
                any(l.pc == end for l in self.labels):
            self.code.append(ir.Exit())
        out: List[ir.Stmt] = []
        for s in self.code:
            if isinstance(s, (ir.IfGoto, ir.Goto)) and isinstance(s.target, _Label):
                s = replace(s, target=s.target.pc)
            out.append(s)
        return out

    # ------------------------------------------------------- statements
    def _stmt(self, n: c_ast.Node) -> None:
        if isinstance(n, c_ast.Compound):
            for s in n.block_items or []:
                self._stmt(s)
        elif isinstance(n, c_ast.Decl):
            raise SubsetError("declarations are only allowed at the top of the function", n)
        elif isinstance(n, c_ast.EmptyStatement):
            pass
        elif isinstance(n, c_ast.ExprList):
            for e in n.exprs:
                self._stmt(e)
        elif isinstance(n, c_ast.Assignment):
            if n.op == "=":
                self._assign(n.lvalue, n.rvalue, n)
            elif n.op in _COMPOUND:
                self._compound(n.lvalue, _COMPOUND[n.op], n.rvalue, n)
            else:
                raise SubsetError(f"unsupported assignment operator '{n.op}'", n)
        elif isinstance(n, c_ast.UnaryOp) and n.op in ("p++", "++", "p--", "--"):
            self._compound(n.expr, "+" if "+" in n.op else "-",
                           c_ast.Constant("int", "1", coord=n.coord), n)
        elif isinstance(n, c_ast.FuncCall):
            self._call_stmt(n)
        elif isinstance(n, c_ast.If):
            l_else = self._new_label()
            self._jump(n.cond, l_else, False)
            self._stmt(n.iftrue)
            if n.iffalse is not None:
                l_end = self._new_label()
                self._emit(ir.Goto(l_end))
                self._place(l_else)
                self._stmt(n.iffalse)
                self._place(l_end)
            else:
                self._place(l_else)
        elif isinstance(n, c_ast.While):
            top, end = self._new_label(), self._new_label()
            self._place(top)
            self._jump(n.cond, end, False)
            self._loop_body(n.stmt, end, top)
            self._emit(ir.Goto(top))
            self._place(end)
        elif isinstance(n, c_ast.DoWhile):
            top, cont, end = self._new_label(), self._new_label(), self._new_label()
            self._place(top)
            self._loop_body(n.stmt, end, cont)
            self._place(cont)
            self._jump(n.cond, top, True)
            self._place(end)
        elif isinstance(n, c_ast.For):
            if isinstance(n.init, c_ast.DeclList):
                raise SubsetError("declarations are not allowed in for-loop headers", n)
            if n.init is not None:
                self._stmt(n.init)
            top, cont, end = self._new_label(), self._new_label(), self._new_label()
            self._place(top)
            if n.cond is not None:
                self._jump(n.cond, end, False)
            self._loop_body(n.stmt, end, cont)
            self._place(cont)
            if n.next is not None:
                self._stmt(n.next)
            self._emit(ir.Goto(top))
            self._place(end)
        elif isinstance(n, c_ast.Break):
            if not self.loops:
                raise SubsetError("'break' outside of a loop", n)
            self._emit(ir.Goto(self.loops[-1][0]))
        elif isinstance(n, c_ast.Continue):
            if not self.loops:
                raise SubsetError("'continue' outside of a loop", n)
            self._emit(ir.Goto(self.loops[-1][1]))
        elif isinstance(n, c_ast.Return):
            if n.expr is not None:
                raise SubsetError("'return' must not carry a value", n)
            self._emit(ir.Exit())
        elif isinstance(n, c_ast.Label):
            lab = self._named(n.name)
            if lab.pc is not None:
                raise SubsetError(f"duplicate label '{n.name}'", n)
            self._place(lab)
            self._stmt(n.stmt)
        elif isinstance(n, c_ast.Goto):
            self._emit(ir.Goto(self._named(n.name)))
        else:
            raise SubsetError(f"unsupported statement ({type(n).__name__})", n)

    def _loop_body(self, body, brk: _Label, cont: _Label) -> None:
        self.loops.append((brk, cont))
        self._stmt(body)
        self.loops.pop()

    def _named(self, name: str) -> _Label:
        if name not in self.named_labels:
            self.named_labels[name] = self._new_label(name)
        return self.named_labels[name]

    def _call_stmt(self, n: c_ast.FuncCall) -> None:
        fname = n.name.name if isinstance(n.name, c_ast.ID) else None
        if fname == "free":
            args = n.args.exprs if n.args else []
            if len(args) != 1:
                raise SubsetError("free takes exactly one argument", n)
            self._emit(ir.Free(self._ptr_var(args[0], "argument of free")))
        elif fname == "malloc":
            raise SubsetError("the result of malloc must be assigned to a pointer variable", n)
        else:
            raise SubsetError(f"function calls are not supported ('{fname}')", n)

    # ------------------------------------------------------ assignments
    def _assign(self, lhs: c_ast.Node, rhs: c_ast.Node, at: c_ast.Node) -> None:
        if isinstance(lhs, c_ast.ID):
            if lhs.name in self.ptr_vars:
                return self._assign_ptr(self.ptr_vars[lhs.name], rhs, at)
            if lhs.name in self.data_vars:
                return self._assign_data(lhs.name, rhs, at)
            raise SubsetError(f"undeclared variable '{lhs.name}'", lhs)
        if isinstance(lhs, c_ast.StructRef):
            p, kind, fid = self._field(lhs)
            if kind == "ptr":
                if self._is_null(rhs):
                    self._emit(ir.StoreNilField(p, fid))
                elif isinstance(rhs, c_ast.ID) and rhs.name in self.ptr_vars:
                    self._emit(ir.StorePtrField(p, fid, self.ptr_vars[rhs.name]))
                else:
                    raise SubsetError("a pointer field can only be assigned NULL or a "
                                      "pointer variable", rhs)
            else:
                ftype = self.data_fields[lhs.field.name].type
                atom, t = self._atom(rhs)
                self._check(t, ftype, rhs, f"field '{lhs.field.name}'")
                self._emit(ir.StoreDataField(p, fid, atom))
            return
        raise SubsetError("left-hand side must be a variable or 'p->field'", lhs)

    def _assign_ptr(self, p: int, rhs: c_ast.Node, at) -> None:
        if self._is_null(rhs):
            self._emit(ir.AssignNil(p))
        elif isinstance(rhs, c_ast.ID) and rhs.name in self.ptr_vars:
            self._emit(ir.AssignPtr(p, self.ptr_vars[rhs.name]))
        elif isinstance(rhs, c_ast.StructRef):
            q, kind, fid = self._field(rhs)
            if kind != "ptr":
                raise SubsetError(f"'{rhs.field.name}' is a data field; cannot assign "
                                  "it to a pointer", rhs)
            self._emit(ir.LoadPtrField(p, q, fid))
        elif self._is_malloc(rhs):
            self._emit(ir.New(p))
        else:
            raise SubsetError("a pointer variable can only be assigned NULL, a pointer "
                              f"variable, 'q->field' or malloc(sizeof(struct "
                              f"{self.struct_name}))", rhs)

    def _assign_data(self, name: str, rhs: c_ast.Node, at) -> None:
        d, dtype = self.data_vars[name]
        if isinstance(rhs, c_ast.StructRef):
            q, kind, fid = self._field(rhs)
            if kind == "ptr":
                raise SubsetError(f"'{rhs.field.name}' is a pointer field; cannot "
                                  "assign it to a data variable", rhs)
            self._check(self.data_fields[rhs.field.name].type, dtype, rhs, f"'{name}'")
            self._emit(ir.LoadDataField(d, q, fid))
            return
        if self._mentions_heap(rhs):
            cond = self._heap_atom(rhs)
            if cond is None:
                raise SubsetError("a heap condition assigned to a variable must be a "
                                  "single comparison (p == q, p != q, p == NULL, "
                                  "p != NULL); combine results with separate "
                                  "statements", rhs)
            if isinstance(cond, ir.FieldIsNil):
                raise SubsetError("a field compared with NULL can only be used as a "
                                  "condition; load the field into a variable first", rhs)
            self._check(DataType.BOOL, dtype, rhs, f"'{name}'")
            self._emit(ir.AssignCond(d, cond))
            return
        e, t = self._dexpr(rhs)
        self._check(t, dtype, rhs, f"'{name}'")
        self._emit(ir.AssignData(d, e))

    def _compound(self, lhs: c_ast.Node, op: str, rhs: c_ast.Node, at) -> None:
        if not (isinstance(lhs, c_ast.ID) and lhs.name in self.data_vars):
            raise SubsetError("compound assignment / ++ / -- only apply to data "
                              "variables", at)
        d, dtype = self.data_vars[lhs.name]
        self._check(dtype, DataType.INT, lhs, f"operator '{op}'")
        e, t = self._dexpr(rhs)
        self._check(t, DataType.INT, rhs, f"operator '{op}'")
        self._emit(ir.AssignData(d, ir.BinOp(op, ir.Var(d), e)))

    # ---------------------------------------------------- heap helpers
    def _ptr_var(self, n: c_ast.Node, what: str) -> int:
        if isinstance(n, c_ast.ID) and n.name in self.ptr_vars:
            return self.ptr_vars[n.name]
        raise SubsetError(f"{what} must be a pointer variable", n)

    def _field(self, n: c_ast.StructRef) -> Tuple[int, str, int]:
        if n.type != "->":
            raise SubsetError("use 'p->field' (the '.' operator is not supported)", n)
        if not isinstance(n.name, c_ast.ID):
            raise SubsetError("chained dereferences are not allowed; use an "
                              "auxiliary pointer variable", n)
        p = self._ptr_var(n.name, "the dereferenced expression")
        f = n.field.name
        if f in self.ptr_fields:
            return p, "ptr", self.ptr_fields[f].id
        if f in self.data_fields:
            return p, "data", self.data_fields[f].id
        raise SubsetError(f"struct {self.struct_name} has no field '{f}'", n)

    @staticmethod
    def _is_null(n: c_ast.Node) -> bool:
        if isinstance(n, c_ast.Cast):
            n = n.expr
        return isinstance(n, c_ast.ID) and n.name == "NULL"

    def _is_malloc(self, n: c_ast.Node) -> bool:
        if isinstance(n, c_ast.Cast):
            if self._classify(n.to_type.type, "cast") != "ptr":
                raise SubsetError("malloc result must be cast to a node pointer", n)
            n = n.expr
        if not (isinstance(n, c_ast.FuncCall) and isinstance(n.name, c_ast.ID)
                and n.name.name == "malloc"):
            return False
        args = n.args.exprs if n.args else []
        ok = (len(args) == 1 and isinstance(args[0], c_ast.UnaryOp)
              and args[0].op == "sizeof" and isinstance(args[0].expr, c_ast.Typename)
              and isinstance(args[0].expr.type, c_ast.TypeDecl)
              and isinstance(args[0].expr.type.type, c_ast.Struct)
              and args[0].expr.type.type.name == self.struct_name)
        if not ok:
            raise SubsetError(f"malloc must be called as malloc(sizeof(struct "
                              f"{self.struct_name}))", n)
        return True

    def _mentions_heap(self, n: c_ast.Node) -> bool:
        if isinstance(n, c_ast.ID):
            return n.name in self.ptr_vars or n.name == "NULL"
        if isinstance(n, (c_ast.StructRef, c_ast.FuncCall)):
            return True
        return any(self._mentions_heap(c) for _, c in n.children())

    def _heap_atom(self, n: c_ast.Node) -> Optional[ir.HeapCond]:
        """Recognise p == q, p != q, p == NULL, p != NULL, p, !atom."""
        if isinstance(n, c_ast.UnaryOp) and n.op == "!":
            inner = self._heap_atom(n.expr)
            return None if inner is None else ir.negate(inner)
        if isinstance(n, c_ast.ID) and n.name in self.ptr_vars:
            return ir.IsNil(self.ptr_vars[n.name], negated=True)
        if isinstance(n, c_ast.StructRef):
            return self._field_is_nil(n, negated=True)
        if isinstance(n, c_ast.BinaryOp) and n.op in _EQ:
            neg = n.op == "!="
            ln, rn = self._is_null(n.left), self._is_null(n.right)
            if isinstance(n.left, c_ast.StructRef) and rn:
                return self._field_is_nil(n.left, neg)
            if ln and isinstance(n.right, c_ast.StructRef):
                return self._field_is_nil(n.right, neg)
            for side in (n.left, n.right):
                if isinstance(side, c_ast.StructRef):
                    raise SubsetError("a field can only be compared with NULL "
                                      "('p->field == NULL'); load the field into a "
                                      "variable first", side)
            lp = isinstance(n.left, c_ast.ID) and n.left.name in self.ptr_vars
            rp = isinstance(n.right, c_ast.ID) and n.right.name in self.ptr_vars
            if lp and rp:
                return ir.PtrEq(self.ptr_vars[n.left.name], self.ptr_vars[n.right.name], neg)
            if lp and rn:
                return ir.IsNil(self.ptr_vars[n.left.name], neg)
            if ln and rp:
                return ir.IsNil(self.ptr_vars[n.right.name], neg)
            if (lp or rp or ln or rn):
                raise SubsetError("pointers can only be compared with pointer "
                                  "variables or NULL", n)
        return None

    def _field_is_nil(self, n: c_ast.StructRef, negated: bool) -> ir.FieldIsNil:
        """p->pf == NULL (or != NULL when negated), pf a pointer field."""
        p, kind, fid = self._field(n)
        if kind != "ptr":
            raise SubsetError(f"'{n.field.name}' is a data field; only pointer fields "
                              "can be compared with NULL", n)
        return ir.FieldIsNil(p, fid, negated)

    # -------------------------------------------------------- conditions
    def _jump(self, n: c_ast.Node, target: _Label, when: bool) -> None:
        """Emit code that jumps to ``target`` iff ``n`` evaluates to ``when``,
        and otherwise falls through."""
        if not self._mentions_heap(n):
            e, t = self._dexpr(n)
            self._check(t, DataType.BOOL, n, "condition")
            c = ir.DataCond(e) if when else ir.negate(ir.DataCond(e))
            if isinstance(c.expr, ir.Const):        # constant folding
                if c.expr.value:
                    self._emit(ir.Goto(target))
                return
            self._emit(ir.IfGoto(c, target))
            return
        if isinstance(n, c_ast.BinaryOp) and n.op in _LOGIC:
            short = n.op == "||"     # value that short-circuits
            if when == short:
                self._jump(n.left, target, when)
                self._jump(n.right, target, when)
            else:
                skip = self._new_label()
                self._jump(n.left, skip, short)
                self._jump(n.right, target, when)
                self._place(skip)
            return
        if isinstance(n, c_ast.UnaryOp) and n.op == "!":
            self._jump(n.expr, target, not when)
            return
        c = self._heap_atom(n)
        if c is None:
            raise SubsetError("unsupported condition: use pointer comparisons, NULL "
                              "checks and Boolean data expressions over variables "
                              "(load fields into variables first)", n)
        self._emit(ir.IfGoto(c if when else ir.negate(c), target))

    # -------------------------------------------------- data expressions
    def _atom(self, n: c_ast.Node) -> Tuple[ir.Atom, DataType]:
        e, t = self._dexpr(n)
        if isinstance(e, ir.UnOp) and e.op == "-" and isinstance(e.operand, ir.Const):
            e = ir.Const(-e.operand.value, DataType.INT)
        if not isinstance(e, (ir.Var, ir.Const)):
            raise SubsetError("a data field can only be assigned a variable or a "
                              "constant; compute the expression into a variable "
                              "first", n)
        return e, t

    def _dexpr(self, n: c_ast.Node) -> Tuple[ir.DataExpr, DataType]:
        if isinstance(n, c_ast.Constant):
            if n.type != "int":
                raise SubsetError(f"unsupported constant type '{n.type}'", n)
            try:
                v = int(n.value.rstrip("uUlL"), 0)
            except ValueError:
                v = int(n.value.rstrip("uUlL"), 8)
            return ir.Const(v, DataType.INT), DataType.INT
        if isinstance(n, c_ast.ID):
            if n.name in ("true", "false"):
                return ir.Const(n.name == "true", DataType.BOOL), DataType.BOOL
            if n.name in self.data_vars:
                d, t = self.data_vars[n.name]
                return ir.Var(d), t
            if n.name in self.ptr_vars or n.name == "NULL":
                raise SubsetError(f"pointer '{n.name}' cannot appear in a data "
                                  "expression", n)
            raise SubsetError(f"undeclared variable '{n.name}'", n)
        if isinstance(n, c_ast.UnaryOp):
            if n.op in ("-", "+"):
                e, t = self._dexpr(n.expr)
                self._check(t, DataType.INT, n, f"unary '{n.op}'")
                return (e if n.op == "+" else ir.UnOp("-", e)), DataType.INT
            if n.op == "!":
                e, t = self._dexpr(n.expr)
                self._check(t, DataType.BOOL, n, "'!'")
                return ir.UnOp("!", e), DataType.BOOL
            raise SubsetError(f"operator '{n.op}' is not allowed inside an expression", n)
        if isinstance(n, c_ast.BinaryOp):
            l, lt = self._dexpr(n.left)
            r, rt = self._dexpr(n.right)
            if n.op in _ARITH:
                self._check(lt, DataType.INT, n.left, f"'{n.op}'")
                self._check(rt, DataType.INT, n.right, f"'{n.op}'")
                return ir.BinOp(n.op, l, r), DataType.INT
            if n.op in _ORDER:
                self._check(lt, DataType.INT, n.left, f"'{n.op}'")
                self._check(rt, DataType.INT, n.right, f"'{n.op}'")
                return ir.BinOp(n.op, l, r), DataType.BOOL
            if n.op in _EQ:
                self._check(rt, lt, n.right, f"'{n.op}'")
                return ir.BinOp(n.op, l, r), DataType.BOOL
            if n.op in _LOGIC:
                self._check(lt, DataType.BOOL, n.left, f"'{n.op}'")
                self._check(rt, DataType.BOOL, n.right, f"'{n.op}'")
                return ir.BinOp(n.op, l, r), DataType.BOOL
            raise SubsetError(f"unsupported operator '{n.op}'", n)
        if isinstance(n, c_ast.StructRef):
            raise SubsetError("field accesses cannot appear inside an expression; "
                              "load the field into a variable first", n)
        raise SubsetError(f"unsupported expression ({type(n).__name__})", n)

    @staticmethod
    def _check(got: DataType, want: DataType, n: c_ast.Node, what: str) -> None:
        if got is not want:
            raise SubsetError(f"type error in {what}: expected {want}, got {got}", n)
