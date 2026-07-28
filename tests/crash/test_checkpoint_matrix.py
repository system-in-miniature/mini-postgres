from pathlib import Path

from minipostgres.engine import Database


def test_reopening_after_repeated_atomic_checkpoints(tmp_path: Path) -> None:
    database = Database.open(tmp_path)
    database.execute("CREATE TABLE values_table (id INT PRIMARY KEY)")
    database.execute("INSERT INTO values_table VALUES (1)")
    first = database.checkpoint()
    database.execute("INSERT INTO values_table VALUES (2)")
    second = database.checkpoint()
    assert second > first
    database._wal.close()
    database._disk.close()
    database._closed = True

    with Database.open(tmp_path) as recovered:
        assert recovered.execute(
            "SELECT id FROM values_table ORDER BY id"
        ).rows == ((1,), (2,))
