from __future__ import annotations

import pytest

from minipostgres.errors import SqlSyntaxError
from minipostgres.sql.ast import BinaryExpr, SelectStmt, UnaryExpr
from minipostgres.sql.parser import parse


def test_and_binds_more_tightly_than_or() -> None:
    statement = parse("SELECT * FROM t WHERE a = 1 OR b = 2 AND c = 3")

    assert isinstance(statement, SelectStmt)
    assert isinstance(statement.where, BinaryExpr)
    assert statement.where.operator == "OR"
    assert isinstance(statement.where.right, BinaryExpr)
    assert statement.where.right.operator == "AND"


def test_arithmetic_and_unary_precedence() -> None:
    statement = parse("SELECT -1 + 2 * 3")

    assert isinstance(statement, SelectStmt)
    expression = statement.items[0].expression
    assert isinstance(expression, BinaryExpr)
    assert expression.operator == "+"
    assert isinstance(expression.left, UnaryExpr)
    assert isinstance(expression.right, BinaryExpr)
    assert expression.right.operator == "*"


def test_parentheses_override_precedence() -> None:
    statement = parse("SELECT (1 + 2) * 3")

    assert isinstance(statement, SelectStmt)
    expression = statement.items[0].expression
    assert isinstance(expression, BinaryExpr)
    assert expression.operator == "*"
    assert isinstance(expression.left, BinaryExpr)
    assert expression.left.operator == "+"


def test_chained_comparison_is_rejected() -> None:
    with pytest.raises(SqlSyntaxError, match="chained comparisons"):
        parse("SELECT 1 < 2 < 3")

