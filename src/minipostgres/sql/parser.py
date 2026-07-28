"""Recursive-descent parser for the frozen MiniPostgres SQL grammar."""

from __future__ import annotations

from typing import NoReturn

from minipostgres.errors import SqlSyntaxError
from minipostgres.sql.ast import (
    AnalyzeStmt,
    Assignment,
    BeginStmt,
    BinaryExpr,
    ColumnDefinition,
    ColumnRef,
    CommitStmt,
    CreateIndexStmt,
    CreateTableStmt,
    DeleteStmt,
    ExplainStmt,
    Expr,
    FunctionCall,
    InsertStmt,
    IsNullExpr,
    JoinClause,
    Literal,
    OrderItem,
    RollbackStmt,
    SelectItem,
    SelectStmt,
    Star,
    Statement,
    TableRef,
    UnaryExpr,
    UpdateStmt,
    VacuumStmt,
)
from minipostgres.sql.lexer import lex
from minipostgres.sql.tokens import Token, TokenKind

_TYPE_NAMES = {
    TokenKind.INT: "INT64",
    TokenKind.INTEGER_TYPE: "INT64",
    TokenKind.BIGINT: "INT64",
    TokenKind.FLOAT_TYPE: "FLOAT64",
    TokenKind.BOOLEAN: "BOOLEAN",
    TokenKind.TEXT: "TEXT",
}

_COMPARISONS = {
    TokenKind.EQ: "=",
    TokenKind.NEQ: "!=",
    TokenKind.LT: "<",
    TokenKind.LTE: "<=",
    TokenKind.GT: ">",
    TokenKind.GTE: ">=",
}


class _Parser:
    def __init__(self, source: str) -> None:
        self._tokens = lex(source)
        self._index = 0

    def parse(self) -> Statement:
        if self._at(TokenKind.EOF):
            self._fail("expected one statement")
        statement = self._statement()
        if self._match(TokenKind.SEMICOLON) and not self._at(TokenKind.EOF):
            self._fail("expected exactly one statement")
        if not self._at(TokenKind.EOF):
            self._fail("expected exactly one statement")
        return statement

    @property
    def _current(self) -> Token:
        return self._tokens[self._index]

    def _at(self, *kinds: TokenKind) -> bool:
        return self._current.kind in kinds

    def _advance(self) -> Token:
        token = self._current
        if token.kind is not TokenKind.EOF:
            self._index += 1
        return token

    def _match(self, *kinds: TokenKind) -> Token | None:
        if self._at(*kinds):
            return self._advance()
        return None

    def _expect(self, kind: TokenKind, label: str) -> Token:
        token = self._match(kind)
        if token is None:
            self._fail(f"expected {label}")
        return token

    def _identifier(self, label: str = "identifier") -> str:
        token = self._expect(TokenKind.IDENT, label)
        assert isinstance(token.value, str)
        return token.value

    def _fail(self, message: str, token: Token | None = None) -> NoReturn:
        target = token or self._current
        raise SqlSyntaxError(f"line {target.line}, column {target.column}: {message}")

    def _statement(self) -> Statement:
        if self._match(TokenKind.CREATE):
            return self._create()
        if self._match(TokenKind.INSERT):
            return self._insert()
        if self._match(TokenKind.SELECT):
            return self._select()
        if self._match(TokenKind.UPDATE):
            return self._update()
        if self._match(TokenKind.DELETE):
            return self._delete()
        if self._match(TokenKind.EXPLAIN):
            analyze = self._match(TokenKind.ANALYZE) is not None
            return ExplainStmt(self._statement(), analyze=analyze)
        if self._match(TokenKind.ANALYZE):
            table = None if self._at_statement_end else self._identifier("table name")
            return AnalyzeStmt(table)
        if self._match(TokenKind.VACUUM):
            table = None if self._at_statement_end else self._identifier("table name")
            return VacuumStmt(table)
        if self._match(TokenKind.BEGIN):
            return BeginStmt()
        if self._match(TokenKind.COMMIT):
            return CommitStmt()
        if self._match(TokenKind.ROLLBACK):
            return RollbackStmt()
        self._fail("expected a supported statement")

    @property
    def _at_statement_end(self) -> bool:
        return self._at(TokenKind.SEMICOLON, TokenKind.EOF)

    def _create(self) -> Statement:
        if self._match(TokenKind.TABLE):
            return self._create_table()
        unique = self._match(TokenKind.UNIQUE) is not None
        self._expect(TokenKind.INDEX, "TABLE or INDEX")
        name = self._identifier("index name")
        self._expect(TokenKind.ON, "ON")
        table = self._identifier("table name")
        self._expect(TokenKind.LPAREN, "'('")
        columns = self._identifier_list()
        self._expect(TokenKind.RPAREN, "')'")
        return CreateIndexStmt(name, table, columns, unique=unique)

    def _create_table(self) -> CreateTableStmt:
        name = self._identifier("table name")
        self._expect(TokenKind.LPAREN, "'('")
        columns = [self._column_definition()]
        while self._match(TokenKind.COMMA):
            columns.append(self._column_definition())
        self._expect(TokenKind.RPAREN, "')'")
        return CreateTableStmt(name, tuple(columns))

    def _column_definition(self) -> ColumnDefinition:
        name = self._identifier("column name")
        type_token = self._current
        type_name = _TYPE_NAMES.get(type_token.kind)
        if type_name is None:
            self._fail("expected column type")
        self._advance()
        nullable = True
        primary_key = False
        unique = False
        seen: set[str] = set()
        while True:
            if self._match(TokenKind.NOT):
                if "nullability" in seen:
                    self._fail("duplicate NULL constraint")
                self._expect(TokenKind.NULL, "NULL after NOT")
                nullable = False
                seen.add("nullability")
            elif self._match(TokenKind.PRIMARY):
                if "primary" in seen:
                    self._fail("duplicate PRIMARY KEY constraint")
                self._expect(TokenKind.KEY, "KEY after PRIMARY")
                primary_key = True
                nullable = False
                unique = True
                seen.add("primary")
            elif self._match(TokenKind.UNIQUE):
                if "unique" in seen:
                    self._fail("duplicate UNIQUE constraint")
                unique = True
                seen.add("unique")
            else:
                break
        return ColumnDefinition(name, type_name, nullable, primary_key, unique)

    def _insert(self) -> InsertStmt:
        self._expect(TokenKind.INTO, "INTO")
        table = self._identifier("table name")
        columns: tuple[str, ...] | None = None
        if self._match(TokenKind.LPAREN):
            columns = self._identifier_list()
            self._expect(TokenKind.RPAREN, "')'")
        self._expect(TokenKind.VALUES, "VALUES")
        rows = [self._expression_row()]
        while self._match(TokenKind.COMMA):
            rows.append(self._expression_row())
        return InsertStmt(table, columns, tuple(rows))

    def _expression_row(self) -> tuple[Expr, ...]:
        self._expect(TokenKind.LPAREN, "'('")
        expressions = [self._expression()]
        while self._match(TokenKind.COMMA):
            expressions.append(self._expression())
        self._expect(TokenKind.RPAREN, "')'")
        return tuple(expressions)

    def _update(self) -> UpdateStmt:
        table = self._identifier("table name")
        self._expect(TokenKind.SET, "SET")
        assignments = [self._assignment()]
        while self._match(TokenKind.COMMA):
            assignments.append(self._assignment())
        where = self._expression() if self._match(TokenKind.WHERE) else None
        return UpdateStmt(table, tuple(assignments), where)

    def _assignment(self) -> Assignment:
        column = self._identifier("column name")
        self._expect(TokenKind.EQ, "'='")
        return Assignment(column, self._expression())

    def _delete(self) -> DeleteStmt:
        self._expect(TokenKind.FROM, "FROM")
        table = self._identifier("table name")
        where = self._expression() if self._match(TokenKind.WHERE) else None
        return DeleteStmt(table, where)

    def _select(self) -> SelectStmt:
        items = [self._select_item()]
        while self._match(TokenKind.COMMA):
            items.append(self._select_item())

        from_table: TableRef | None = None
        joins: list[JoinClause] = []
        if self._match(TokenKind.FROM):
            from_table = self._table_ref()
            while self._at(TokenKind.INNER, TokenKind.JOIN):
                self._match(TokenKind.INNER)
                self._expect(TokenKind.JOIN, "JOIN")
                table = self._table_ref()
                self._expect(TokenKind.ON, "ON")
                joins.append(JoinClause(table, self._expression()))

        where = self._expression() if self._match(TokenKind.WHERE) else None
        group_by: tuple[Expr, ...] = ()
        if self._match(TokenKind.GROUP):
            self._expect(TokenKind.BY, "BY after GROUP")
            group_by = self._expression_list()

        order_by: tuple[OrderItem, ...] = ()
        if self._match(TokenKind.ORDER):
            self._expect(TokenKind.BY, "BY after ORDER")
            orders = [self._order_item()]
            while self._match(TokenKind.COMMA):
                orders.append(self._order_item())
            order_by = tuple(orders)

        limit: int | None = None
        if self._match(TokenKind.LIMIT):
            token = self._expect(TokenKind.INTEGER, "non-negative integer")
            assert isinstance(token.value, int)
            limit = token.value

        return SelectStmt(
            tuple(items),
            from_table,
            tuple(joins),
            where,
            group_by,
            order_by,
            limit,
        )

    def _select_item(self) -> SelectItem:
        expression = self._expression()
        alias: str | None = None
        if self._match(TokenKind.AS) or self._at(TokenKind.IDENT):
            alias = self._identifier("alias")
        return SelectItem(expression, alias)

    def _table_ref(self) -> TableRef:
        name = self._identifier("table name")
        alias: str | None = None
        if self._match(TokenKind.AS) or self._at(TokenKind.IDENT):
            alias = self._identifier("table alias")
        return TableRef(name, alias)

    def _order_item(self) -> OrderItem:
        expression = self._expression()
        direction = "ASC"
        if self._match(TokenKind.ASC):
            direction = "ASC"
        elif self._match(TokenKind.DESC):
            direction = "DESC"
        nulls: str | None = None
        if self._match(TokenKind.NULLS):
            if self._match(TokenKind.FIRST):
                nulls = "FIRST"
            elif self._match(TokenKind.LAST):
                nulls = "LAST"
            else:
                self._fail("expected FIRST or LAST after NULLS")
        return OrderItem(expression, direction, nulls)

    def _identifier_list(self) -> tuple[str, ...]:
        values = [self._identifier()]
        while self._match(TokenKind.COMMA):
            values.append(self._identifier())
        return tuple(values)

    def _expression_list(self) -> tuple[Expr, ...]:
        values = [self._expression()]
        while self._match(TokenKind.COMMA):
            values.append(self._expression())
        return tuple(values)

    def _expression(self) -> Expr:
        return self._or()

    def _or(self) -> Expr:
        expression = self._and()
        while self._match(TokenKind.OR):
            expression = BinaryExpr(expression, "OR", self._and())
        return expression

    def _and(self) -> Expr:
        expression = self._not()
        while self._match(TokenKind.AND):
            expression = BinaryExpr(expression, "AND", self._not())
        return expression

    def _not(self) -> Expr:
        if self._match(TokenKind.NOT):
            return UnaryExpr("NOT", self._not())
        return self._comparison()

    def _comparison(self) -> Expr:
        expression = self._additive()
        if self._match(TokenKind.IS):
            negated = self._match(TokenKind.NOT) is not None
            self._expect(TokenKind.NULL, "NULL after IS")
            return IsNullExpr(expression, negated)
        operator = _COMPARISONS.get(self._current.kind)
        if operator is None:
            return expression
        self._advance()
        expression = BinaryExpr(expression, operator, self._additive())
        if self._at(*_COMPARISONS, TokenKind.IS):
            self._fail("chained comparisons are not supported")
        return expression

    def _additive(self) -> Expr:
        expression = self._multiplicative()
        while self._at(TokenKind.PLUS, TokenKind.MINUS):
            operator = self._advance().lexeme
            expression = BinaryExpr(expression, operator, self._multiplicative())
        return expression

    def _multiplicative(self) -> Expr:
        expression = self._unary()
        while self._at(TokenKind.STAR, TokenKind.SLASH):
            operator = self._advance().lexeme
            expression = BinaryExpr(expression, operator, self._unary())
        return expression

    def _unary(self) -> Expr:
        if self._at(TokenKind.PLUS, TokenKind.MINUS):
            return UnaryExpr(self._advance().lexeme, self._unary())
        return self._primary()

    def _primary(self) -> Expr:
        if token := self._match(
            TokenKind.INTEGER,
            TokenKind.FLOAT,
            TokenKind.STRING,
        ):
            return Literal(token.value)
        if self._match(TokenKind.NULL):
            return Literal(None)
        if self._match(TokenKind.TRUE):
            return Literal(True)
        if self._match(TokenKind.FALSE):
            return Literal(False)
        if self._match(TokenKind.STAR):
            return Star()
        if self._match(TokenKind.LPAREN):
            expression = self._expression()
            self._expect(TokenKind.RPAREN, "')'")
            return expression
        if self._at(TokenKind.IDENT):
            name = self._identifier()
            if self._match(TokenKind.LPAREN):
                arguments: list[Expr] = []
                if not self._at(TokenKind.RPAREN):
                    arguments.append(self._expression())
                    while self._match(TokenKind.COMMA):
                        arguments.append(self._expression())
                self._expect(TokenKind.RPAREN, "')'")
                return FunctionCall(name.upper(), tuple(arguments))
            if self._match(TokenKind.DOT):
                if self._match(TokenKind.STAR):
                    return Star(name)
                column = self._identifier("column name")
                return ColumnRef(column, table=name)
            return ColumnRef(name)
        self._fail("expected expression")


def parse(source: str) -> Statement:
    """Parse exactly one statement from SQL text."""

    return _Parser(source).parse()
