from __future__ import annotations

from minipostgres.engine import Database


def test_join_group_and_aggregate_end_to_end(engine: Database) -> None:
    engine.execute("CREATE TABLE users (id INT NOT NULL, name TEXT)")
    engine.execute("CREATE TABLE orders (id INT NOT NULL, user_id INT, total INT)")
    engine.execute("INSERT INTO users VALUES (1, 'A'), (2, 'B')")
    engine.execute("INSERT INTO orders VALUES (10, 1, 10), (11, 1, 20), (12, 2, 7)")

    result = engine.execute(
        "SELECT u.name, COUNT(o.id), SUM(o.total) "
        "FROM users u INNER JOIN orders o ON u.id = o.user_id "
        "GROUP BY u.name ORDER BY u.name"
    )

    assert result.columns == ("name", "count", "sum")
    assert result.rows == (("A", 2, 30), ("B", 1, 7))
