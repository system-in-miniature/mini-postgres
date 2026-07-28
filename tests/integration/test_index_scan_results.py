from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database


def test_index_scan_rechecks_complete_heap_predicate(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE users "
            "(id INT PRIMARY KEY, active BOOLEAN, payload TEXT)"
        )
        for start in range(0, 300, 50):
            values = ", ".join(
                f"({value}, "
                f"{'TRUE' if value % 2 == 0 else 'FALSE'}, "
                f"'{'x' * 200}')"
                for value in range(start, start + 50)
            )
            database.execute(f"INSERT INTO users VALUES {values}")
        database.execute("ANALYZE users")

        result = database.execute(
            "SELECT id FROM users "
            "WHERE id >= 10 AND id < 20 AND active = TRUE "
            "ORDER BY id"
        )

        assert result.rows == ((10,), (12,), (14,), (16,), (18,))


def test_index_scan_skips_candidates_removed_from_heap(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE users (id INT PRIMARY KEY, payload TEXT)"
        )
        database.execute(
            "INSERT INTO users VALUES "
            + ", ".join(
                f"({value}, '{'x' * 200}')"
                for value in range(300)
            )
        )
        database.execute("ANALYZE users")
        database.execute("DELETE FROM users WHERE id = 7")

        assert database.execute(
            "SELECT id FROM users WHERE id = 7"
        ).rows == ()
