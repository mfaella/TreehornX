import re
from collections import ChainMap, deque
from dataclasses import dataclass, field
from itertools import islice
from typing import override

from antlr4 import ParserRuleContext
from antlr4.tree.Tree import TerminalNodeImpl

from treehornx.chc.ppcompiler._internal.prepost_nodes import *
from treehornx.chc.ppcompiler.grammar.PrePostLangParser import PrePostLangParser
from treehornx.chc.ppcompiler.grammar.PrePostLangVisitor import PrePostLangVisitor


@dataclass
class _PPLangProgramVisitor(PrePostLangVisitor):
    _result: deque[AstNode] = field(init=False, default_factory=deque)

    def _push(self, result: AstNode):
        self._result.append(result)

    def _pop(self) -> AstNode:
        return self._result.pop()

    def _get_id_rule_data(self, ctx: PrePostLangParser.IdContext) -> tuple[str, int, int]:
        id_token = next(filter(None, (ctx.ID(), ctx.VAR(), ctx.LET())), None)
        if id_token is None:
            raise ValueError(f"Expected an ID, VAR, or LET token in Id context, but got none. Context: {ctx}")
        assert isinstance(id_token, TerminalNodeImpl)
        return id_token.getText(), id_token.symbol.line, id_token.symbol.column

    def _visit_unary_operator(
        self, ctx: ParserRuleContext, operand_ctx: ParserRuleContext, has_op_token: bool, opcls: type[UnaryOperator]
    ):
        assert operand_ctx is not None
        self.visit(operand_ctx)
        operand_node = self._pop()

        if not has_op_token:
            self._push(operand_node)
            return

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column

        op_node = opcls(text, line, column, operand_node)
        self._push(op_node)

    def _visit_binary_operator(
        self,
        ctx: ParserRuleContext,
        left_ctx: ParserRuleContext,
        right_ctx: ParserRuleContext | None,
        opcls: type[BinaryOperator],
    ):
        assert left_ctx is not None
        self.visit(left_ctx)
        left_node = self._pop()

        if not right_ctx:
            self._push(left_node)
            return

        assert right_ctx is not None
        self.visit(right_ctx)
        right_node = self._pop()

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column

        op_node = opcls(text, line, column, left_node, right_node)
        self._push(op_node)

    @override
    def visitVarDecl(self, ctx: PrePostLangParser.VarDeclContext):
        ctx_id = ctx.id_()
        assert ctx_id is not None
        id_str, id_line, id_column = self._get_id_rule_data(ctx_id)
        id_node = Id(id_str, id_line, id_column)
        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        node = VarDecl(text, line, column, id_node)
        self._push(node)

    @override
    def visitEnumDecl(self, ctx: PrePostLangParser.EnumDeclContext):
        ctx_id = ctx.id_()
        assert ctx_id is not None
        id_str, id_line, id_column = self._get_id_rule_data(ctx_id)
        id_node = Id(id_str, id_line, id_column)
        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        enum_node = EnumDecl(text, line, column, id_node)
        self._push(enum_node)

    @override
    def visitLetDeclWithParams(self, ctx: PrePostLangParser.LetDeclWithParamsContext):
        # ctx.id_() returns a list of contexts if the index is not specified, but the stub files do not aseert it
        ctx_id = ctx.id_(0)
        assert ctx_id is not None
        id_str, id_line, id_column = self._get_id_rule_data(ctx_id)
        id_node = Id(id_str, id_line, id_column)
        param_id_nodes: list[Id] = []
        for param_ctx in islice(ctx.id_(), 1, None):  # pyright: ignore
            assert param_ctx is not None and isinstance(param_ctx, PrePostLangParser.IdContext)
            param_str, pline, pcolumn = self._get_id_rule_data(param_ctx)
            param_id_nodes.append(Id(param_str, pline, pcolumn))

        expr_ctx = ctx.expr()
        assert expr_ctx is not None
        self.visit(expr_ctx)
        body_node = self._pop()

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        macro_decl_node = MacroDecl(text, line, column, id_node, tuple(param_id_nodes), body_node)
        self._push(macro_decl_node)

    @override
    def visitLetDeclNoParam(self, ctx: PrePostLangParser.LetDeclNoParamContext):
        # ctx.id_() returns a list of contexts if the index is not specified, but the stub files do not aseert it
        ctx_id = ctx.id_()
        assert ctx_id is not None
        id_str, id_line, id_column = self._get_id_rule_data(ctx_id)
        id_node = Id(id_str, id_line, id_column)

        expr_ctx = ctx.expr()
        assert expr_ctx is not None
        self.visit(expr_ctx)
        body_node = self._pop()

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        macro_decl_node = MacroDecl(text, line, column, id_node, (), body_node)
        self._push(macro_decl_node)

    @override
    def visitProgram(self, ctx: PrePostLangParser.ProgramContext): ...

    @override
    def visitStatement(self, ctx: PrePostLangParser.StatementContext): ...

    @override
    def visitLetDecl(self, ctx: PrePostLangParser.LetDeclContext): ...

    @override
    def visitExpr(self, ctx: PrePostLangParser.ExprContext): ...

    @override
    def visitBExpr(self, ctx: PrePostLangParser.BExprContext): ...

    @override
    def visitOrExpr(self, ctx: PrePostLangParser.OrExprContext):
        and_ctx = ctx.andExpr()
        assert and_ctx
        self._visit_binary_operator(ctx, and_ctx, ctx.orExpr(), Or)

    @override
    def visitAndExpr(self, ctx: PrePostLangParser.AndExprContext):
        not_ctx = ctx.notExpr()
        assert not_ctx
        self._visit_binary_operator(ctx, not_ctx, ctx.andExpr(), And)

    @override
    def visitBCmpExpr(self, ctx: PrePostLangParser.BCmpExprContext):
        left_ctx = ctx.notExpr(0)
        right_ctx = ctx.notExpr(1)
        assert left_ctx is not None and right_ctx is not None
        self._visit_binary_operator(ctx, left_ctx, right_ctx, Iff)

    @override
    def visitNotExpr(self, ctx: PrePostLangParser.NotExprContext):
        term_ctx = ctx.bTerm()
        assert term_ctx is not None
        self._visit_unary_operator(ctx, term_ctx, bool(ctx.NOT()), Not)

    @override
    def visitTrue(self, ctx: PrePostLangParser.TrueContext):
        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        true_node = T(text, line, column)
        self._push(true_node)

    @override
    def visitFalse(self, ctx: PrePostLangParser.FalseContext):
        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        false_node = F(text, line, column)
        self._push(false_node)

    @override
    def visitParent(self, ctx: PrePostLangParser.ParentContext):
        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        parent_node = Parent(text, line, column)
        self._push(parent_node)

    @override
    def visitParentQ(self, ctx: PrePostLangParser.ParentQContext):
        parent_q_token = ctx.PARENT_Q()
        assert parent_q_token and isinstance(parent_q_token, TerminalNodeImpl)
        parent_q_name = parent_q_token.getText()
        q_name = parent_q_name[2:]  # remove the "#:" prefix
        text, line, column = parent_q_token.getText(), parent_q_token.symbol.line, parent_q_token.symbol.column
        parent_state_node = ParentState(text, line, column, q_name)
        self._push(parent_state_node)

    @override
    def visitField(self, ctx: PrePostLangParser.FieldContext):
        field_token = ctx.FIELD()
        assert field_token and isinstance(field_token, TerminalNodeImpl)
        field_name = field_token.getText()
        text, line, column = field_token.getText(), field_token.symbol.line, field_token.symbol.column
        field_node = Field(text, line, column, field_name[1:])  # remove the "#" prefix
        self._push(field_node)

    @override
    def visitFieldQ(self, ctx: PrePostLangParser.FieldQContext):
        field_q_token = ctx.FIELD_Q()
        assert field_q_token and isinstance(field_q_token, TerminalNodeImpl)
        field_q_name = field_q_token.getText()
        match = re.match(r"^#([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)$", field_q_name)
        assert match
        field_name, q_name = match.group(1), match.group(2)
        text, line, column = field_q_token.getText(), field_q_token.symbol.line, field_q_token.symbol.column
        field_state_node = FieldState(text, line, column, field_name, q_name)
        self._push(field_state_node)

    @override
    def visitNodeQ(self, ctx: PrePostLangParser.NodeQContext):
        node_q_token = ctx.NODE_Q()
        assert node_q_token and isinstance(node_q_token, TerminalNodeImpl)
        node_q_name = node_q_token.getText()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):([A-Za-z_][A-Za-z0-9_]*)$", node_q_name)
        assert match
        node_name, q_name = match.group(1), match.group(2)
        text, line, column = node_q_token.getText(), node_q_token.symbol.line, node_q_token.symbol.column
        node_state_node = NodeState(text, line, column, node_name, q_name)
        self._push(node_state_node)

    @override
    def visitIsNil(self, ctx: PrePostLangParser.IsNilContext):
        node_atom_ctx = ctx.nodeAtom()
        assert node_atom_ctx is not None
        self._visit_unary_operator(ctx, node_atom_ctx, True, IsNil)

    @override
    def visitIsRoot(self, ctx: PrePostLangParser.IsRootContext):
        node_atom_ctx = ctx.nodeAtom()
        assert node_atom_ctx is not None
        self._visit_unary_operator(ctx, node_atom_ctx, True, IsRoot)

    @override
    def visitIsLeaf(self, ctx: PrePostLangParser.IsLeafContext):
        node_atom_ctx = ctx.nodeAtom()
        assert node_atom_ctx is not None
        self._visit_unary_operator(ctx, node_atom_ctx, True, IsLeaf)

    @override
    def visitApplication(self, ctx: PrePostLangParser.ApplicationContext):
        id_ctx = ctx.id_()
        assert id_ctx is not None
        id_str, id_line, id_column = self._get_id_rule_data(id_ctx)
        id_node = Id(id_str, id_line, id_column)

        arg_nodes: list[AstNode] = []
        # The stub files do not assert that ctx.arg() returns a list of contexts if the index is not specified,
        # but the grammar allows for multiple arguments, so we have to ignore the type checker here
        for arg_ctx in ctx.arg():  # pyright: ignore
            assert isinstance(arg_ctx, PrePostLangParser.ArgContext)
            self.visit(arg_ctx)
            arg_node = self._pop()
            arg_nodes.append(arg_node)

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        application_node = Application(text, line, column, id_node, tuple(arg_nodes))
        self._push(application_node)

    @override
    def visitACmpExpr(self, ctx: PrePostLangParser.ACmpExprContext):
        left_ctx = ctx.aExpr(0)
        right_ctx = ctx.aExpr(1)
        assert left_ctx is not None and right_ctx is not None

        opcls = None
        if ctx.EQ():
            opcls = Eq
        elif ctx.LT():
            opcls = Lt
        elif ctx.LE():
            opcls = Le
        elif ctx.GT():
            opcls = Gt
        elif ctx.GE():
            opcls = Ge
        else:
            raise ValueError("Invalid comparison operator in ACmpExpr")

        self._visit_binary_operator(ctx, left_ctx, right_ctx, opcls)

    @override
    def visitBIteExpr(self, ctx: PrePostLangParser.BIteExprContext):
        cond_ctx = ctx.bExpr(0)
        then_branch_ctx = ctx.bExpr(1)
        else_branch_ctx = ctx.bExpr(2)
        assert cond_ctx is not None and then_branch_ctx is not None and else_branch_ctx is not None
        self.visit(cond_ctx)
        self.visit(then_branch_ctx)
        self.visit(else_branch_ctx)

        else_node = self._pop()
        then_node = self._pop()
        cond_node = self._pop()

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        ite_node = IfThenElse(text, line, column, cond_node, then_node, else_node)
        self._push(ite_node)

    @override
    def visitBItExpr(self, ctx: PrePostLangParser.BItExprContext):
        cond_ctx = ctx.bExpr(0)
        then_branch_ctx = ctx.bExpr(1)
        assert cond_ctx is not None and then_branch_ctx is not None
        self.visit(cond_ctx)
        self.visit(then_branch_ctx)

        else_node = self._pop()
        then_node = self._pop()
        cond_node = self._pop()

        assert ctx.start
        text, line, column = ctx.getText(), ctx.start.line, ctx.start.column
        ite_node = IfThen(text, line, column, cond_node, then_node)
        self._push(ite_node)

    @override
    def visitASumExpr(self, ctx: PrePostLangParser.ASumExprContext):
        mul_ctx = ctx.aMulExpr()
        assert mul_ctx is not None
        self._visit_binary_operator(ctx, mul_ctx, ctx.aSumExpr(), Add)

    @override
    def visitAMulExpr(self, ctx: PrePostLangParser.AMulExprContext):
        neg_ctx = ctx.aNegExpr()
        assert neg_ctx is not None
        self._visit_binary_operator(ctx, neg_ctx, ctx.aMulExpr(), Mul)

    @override
    def visitANegExpr(self, ctx: PrePostLangParser.ANegExprContext):
        term_ctx = ctx.aTerm()
        assert term_ctx is not None
        self._visit_unary_operator(ctx, term_ctx, bool(ctx.MINUS()), Neg)

    @override
    def visitNat(self, ctx: PrePostLangParser.NatContext):
        token = ctx.NATURAL()
        assert isinstance(token, TerminalNodeImpl)
        text, line, column = token.getText(), token.symbol.line, token.symbol.column
        value = int(text)
        nat_node = Nat(text, line, column, value)
        self._push(nat_node)

    @override
    def visitEnumVariant(self, ctx: PrePostLangParser.EnumVariantContext):
        token = ctx.ENUM_VARIANT()
        assert isinstance(token, TerminalNodeImpl)
        text, line, column = token.getText(), token.symbol.line, token.symbol.column
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)::([A-Za-z_][A-Za-z0-9_]*)$", text)
        assert match
        type_name, variant_name = match.group(1), match.group(2)
        enum_variant_node = EnumIVariant(text, line, column, type_name, variant_name)
        self._push(enum_variant_node)

    def stmts(self) -> tuple[AstNode, ...]:
        return tuple(self._result)

def ast(tree: PrePostLangParser.ProgramContext) -> tuple[AstNode, ...]:
    visitor = _PPLangProgramVisitor()
    visitor.visit(tree)
    return visitor.stmts()
