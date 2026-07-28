from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.engine import Database
from minipostgres.errors import ConstraintViolation


def test_unique_index_tracks_update_and_delete_without_partial_insert(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT, name TEXT)")
        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
        database.execute("CREATE UNIQUE INDEX users_id ON users (id)")

        with pytest.raises(ConstraintViolation):
            database.execute(
                "INSERT INTO users VALUES (3, 'C'), (2, 'duplicate')"
            )
        assert database.execute(
            "SELECT id FROM users ORDER BY id"
        ).rows == ((1,), (2,))

        database.execute("UPDATE users SET id = 3 WHERE id = 1")
        database.execute("INSERT INTO users VALUES (1, 'new owner')")
        database.execute("DELETE FROM users WHERE id = 2")
        database.execute("INSERT INTO users VALUES (2, 'reused')")

        assert database.execute(
            "SELECT id FROM users ORDER BY id"
        ).rows == ((1,), (2,), (3,))


def test_frozen_index_scope_rejects_null_keys(tmp_path: Path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE optional_values (value INT)")
        database.execute("INSERT INTO optional_values VALUES (NULL)")

        with pytest.raises(ConstraintViolation, match="NULL index key"):
            database.execute(
                "CREATE INDEX optional_value_idx ON optional_values (value)"
            )
