from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.engine import Database
from minipostgres.errors import ConstraintViolation


def test_primary_key_and_unique_columns_are_enforced_without_explicit_index(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE users ("
            "id INT PRIMARY KEY, email TEXT UNIQUE, display_name TEXT)"
        )
        database.execute("INSERT INTO users VALUES (1, 'a@example.com', 'A')")

        with pytest.raises(ConstraintViolation, match="unique"):
            database.execute(
                "INSERT INTO users VALUES (1, 'b@example.com', 'duplicate id')"
            )
        with pytest.raises(ConstraintViolation, match="unique"):
            database.execute(
                "INSERT INTO users VALUES (2, 'a@example.com', 'duplicate email')"
            )

        assert database.execute(
            "SELECT id, email FROM users"
        ).rows == ((1, "a@example.com"),)


def test_schema_unique_constraints_survive_restart(tmp_path: Path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE accounts (id INT PRIMARY KEY)")
        database.execute("INSERT INTO accounts VALUES (7)")

    with (
        Database.open(tmp_path) as reopened,
        pytest.raises(ConstraintViolation, match="unique"),
    ):
        reopened.execute("INSERT INTO accounts VALUES (7)")
