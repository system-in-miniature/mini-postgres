from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database


def test_phase_b_rows_survive_clean_restart(tmp_path: Path) -> None:
    with Database.open(tmp_path, buffer_frames=3) as database:
        database.execute("CREATE TABLE users (id INT, name TEXT)")
        database.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
        database.execute("UPDATE users SET name = 'Bee' WHERE id = 2")
    with Database.open(tmp_path, buffer_frames=2) as database:
        assert database.execute(
            "SELECT * FROM users ORDER BY id"
        ).rows == ((1, "A"), (2, "Bee"))
        database.execute("DELETE FROM users WHERE id = 1")
    with Database.open(tmp_path, buffer_frames=1) as database:
        assert database.execute("SELECT * FROM users").rows == ((2, "Bee"),)


def test_empty_table_has_a_durable_heap_before_catalog_publication(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE items (id INT)")

    assert (tmp_path / "relations" / "table-1.heap").exists()
    with Database.open(tmp_path) as database:
        assert database.execute("SELECT * FROM items").rows == ()

