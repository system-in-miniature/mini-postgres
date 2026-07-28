from __future__ import annotations

from pathlib import Path

from minipostgres.engine import Database


def test_hash_join_rechecks_non_key_conjuncts(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE left_items (id INT, enabled BOOLEAN)"
        )
        database.execute(
            "CREATE TABLE right_items (id INT, amount INT)"
        )
        database.execute(
            "INSERT INTO left_items VALUES "
            + ", ".join(
                f"({value}, {'TRUE' if value % 2 == 0 else 'FALSE'})"
                for value in range(100)
            )
        )
        database.execute(
            "INSERT INTO right_items VALUES "
            + ", ".join(
                f"({value}, {value * 10})"
                for value in range(100)
            )
        )
        database.execute("ANALYZE")

        result = database.execute(
            "SELECT l.id, r.amount FROM left_items l "
            "JOIN right_items r "
            "ON l.id = r.id AND l.enabled = TRUE "
            "ORDER BY l.id"
        )

        assert result.rows == tuple(
            (value, value * 10) for value in range(0, 100, 2)
        )


def test_nested_loop_nonequality_join_returns_same_relational_semantics(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE a (id INT)")
        database.execute("CREATE TABLE b (id INT)")
        database.execute("INSERT INTO a VALUES (1), (2), (3)")
        database.execute("INSERT INTO b VALUES (2), (3), (4)")
        database.execute("ANALYZE")

        result = database.execute(
            "SELECT a.id, b.id FROM a JOIN b ON a.id < b.id "
            "ORDER BY a.id, b.id"
        )

        assert result.rows == (
            (1, 2),
            (1, 3),
            (1, 4),
            (2, 3),
            (2, 4),
            (3, 4),
        )
