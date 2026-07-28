from __future__ import annotations

import pytest

from minipostgres.errors import SqlSyntaxError
from minipostgres.sql.ast import (
    AnalyzeStmt,
    BeginStmt,
    CommitStmt,
    CreateIndexStmt,
    CreateTableStmt,
    DeleteStmt,
    ExplainStmt,
    InsertStmt,
    RollbackStmt,
    UpdateStmt,
    VacuumStmt,
)
from minipostgres.sql.parser import parse


def test_parse_create_table_constraints() -> None:
    statement = parse(
        "CREATE TABLE users ("
        "id INT PRIMARY KEY, name TEXT NOT NULL, score FLOAT, active BOOLEAN"
        ");"
    )

    assert isinstance(statement, CreateTableStmt)
    assert statement.name == "users"
    assert [column.type_name for column in statement.columns] == [
        "INT64",
        "TEXT",
        "FLOAT64",
        "BOOLEAN",
    ]
    assert statement.columns[0].primary_key
    assert not statement.columns[1].nullable


def test_parse_create_unique_index() -> None:
    statement = parse("CREATE UNIQUE INDEX users_name ON users (name)")

    assert isinstance(statement, CreateIndexStmt)
    assert statement.unique
    assert statement.columns == ("name",)


def test_parse_insert_multiple_rows_and_optional_columns() -> None:
    statement = parse(
        "INSERT INTO users (id, name) VALUES (1, 'A'), (2, NULL)"
    )

    assert isinstance(statement, InsertStmt)
    assert statement.columns == ("id", "name")
    assert len(statement.rows) == 2
    assert statement.rows[1][1].value is None


def test_parse_update_and_delete() -> None:
    update = parse("UPDATE users SET name = 'B', score = score + 1 WHERE id = 2")
    delete = parse("DELETE FROM users WHERE active = FALSE")

    assert isinstance(update, UpdateStmt)
    assert [assignment.column for assignment in update.assignments] == [
        "name",
        "score",
    ]
    assert update.where is not None
    assert isinstance(delete, DeleteStmt)
    assert delete.where is not None


def test_parse_control_maintenance_and_explain_statements() -> None:
    assert isinstance(parse("BEGIN"), BeginStmt)
    assert isinstance(parse("COMMIT"), CommitStmt)
    assert isinstance(parse("ROLLBACK"), RollbackStmt)
    assert isinstance(parse("ANALYZE users"), AnalyzeStmt)
    assert isinstance(parse("VACUUM"), VacuumStmt)
    explain = parse("EXPLAIN ANALYZE DELETE FROM users")
    assert isinstance(explain, ExplainStmt)
    assert explain.analyze
    assert isinstance(explain.statement, DeleteStmt)


def test_parser_requires_exactly_one_complete_statement() -> None:
    with pytest.raises(SqlSyntaxError, match="one statement"):
        parse("SELECT 1; SELECT 2")
    with pytest.raises(SqlSyntaxError, match="expected"):
        parse("INSERT INTO users VALUES (1")

