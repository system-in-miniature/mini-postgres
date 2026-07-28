from __future__ import annotations

from minipostgres.sql.ast import (
    BinaryExpr,
    ColumnRef,
    FunctionCall,
    SelectStmt,
    Star,
)
from minipostgres.sql.parser import parse


def test_parse_select_join_group_order_limit() -> None:
    statement = parse(
        "SELECT u.name, COUNT(o.id) AS n "
        "FROM users u INNER JOIN orders AS o ON u.id = o.user_id "
        "WHERE o.total >= 10 GROUP BY u.name "
        "ORDER BY n DESC NULLS FIRST LIMIT 5"
    )

    assert isinstance(statement, SelectStmt)
    assert statement.from_table is not None
    assert statement.from_table.alias == "u"
    assert len(statement.joins) == 1
    assert statement.joins[0].table.alias == "o"
    assert statement.limit == 5
    assert statement.order_by[0].direction == "DESC"
    assert statement.order_by[0].nulls == "FIRST"
    aggregate = statement.items[1].expression
    assert isinstance(aggregate, FunctionCall)
    assert aggregate.name == "COUNT"


def test_parse_select_star_qualified_star_and_expression_only_select() -> None:
    star = parse("SELECT *, u.* FROM users u")
    expression_only = parse("SELECT 1 + 2 AS answer")

    assert isinstance(star, SelectStmt)
    assert isinstance(star.items[0].expression, Star)
    assert star.items[1].expression == Star("u")
    assert isinstance(expression_only, SelectStmt)
    assert expression_only.from_table is None
    assert expression_only.items[0].alias == "answer"


def test_parse_is_null_and_boolean_literals() -> None:
    statement = parse(
        "SELECT id FROM users WHERE deleted_at IS NULL OR active = TRUE"
    )

    assert isinstance(statement, SelectStmt)
    assert isinstance(statement.where, BinaryExpr)
    assert statement.where.operator == "OR"


def test_column_reference_preserves_qualification() -> None:
    statement = parse("SELECT Users.ID FROM Users")

    assert isinstance(statement, SelectStmt)
    reference = statement.items[0].expression
    assert reference == ColumnRef(name="ID", table="Users")

