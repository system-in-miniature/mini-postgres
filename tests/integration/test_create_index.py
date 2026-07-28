from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.engine import Database
from minipostgres.errors import ConstraintViolation


def test_create_unique_index_builds_existing_rows_before_publication(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT, name TEXT)")
        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
        database.execute("CREATE UNIQUE INDEX users_id ON users (id)")

        with pytest.raises(ConstraintViolation):
            database.execute("INSERT INTO users VALUES (1, 'duplicate')")
        assert database.catalog.index("users_id").unique

    assert (tmp_path / "indexes" / "index-1.btree").exists()
    with Database.open(tmp_path) as reopened, pytest.raises(ConstraintViolation):
        reopened.execute("INSERT INTO users VALUES (2, 'duplicate')")


def test_failed_unique_build_is_not_published(tmp_path: Path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT, name TEXT)")
        database.execute("INSERT INTO users VALUES (1, 'A'), (1, 'B')")

        with pytest.raises(ConstraintViolation, match="unique"):
            database.execute("CREATE UNIQUE INDEX users_id ON users (id)")

        assert database.catalog.indexes() == ()


def test_nonunique_index_accepts_duplicate_keys(tmp_path: Path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE events (kind TEXT, value INT)")
        database.execute("INSERT INTO events VALUES ('click', 1), ('click', 2)")

        assert (
            database.execute("CREATE INDEX events_kind ON events (kind)").command_tag
            == "CREATE INDEX"
        )
        database.execute("INSERT INTO events VALUES ('click', 3)")

        assert database.execute(
            "SELECT value FROM events ORDER BY value"
        ).rows == ((1,), (2,), (3,))

