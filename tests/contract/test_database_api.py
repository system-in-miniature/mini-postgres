from __future__ import annotations

import pytest

from minipostgres.engine import Database
from minipostgres.errors import DatabaseClosed


def test_database_executes_query_loop_across_statements(tmp_path) -> None:
    with Database.open(tmp_path) as db:
        result = db.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
        assert result.command_tag == "CREATE TABLE"
        assert (
            db.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')").command_tag
            == "INSERT 0 2"
        )

        selected = db.execute(
            "SELECT name FROM users WHERE id >= 1 ORDER BY id DESC LIMIT 1"
        )

        assert selected.columns == ("name",)
        assert selected.rows == (("B",),)
        assert selected.command_tag == "SELECT 1"


def test_close_is_idempotent_and_operations_fail_after_close(tmp_path) -> None:
    db = Database.open(tmp_path)

    db.close()
    db.close()

    with pytest.raises(DatabaseClosed):
        db.execute("SELECT 1")
