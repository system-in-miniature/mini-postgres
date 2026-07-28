from pathlib import Path

from minipostgres.engine import Database
from minipostgres.storage.disk import relation_path
from minipostgres.storage.identifiers import btree_relation


def _crash_without_cleanup(database: Database) -> None:
    database._wal.close()
    database._disk.close()
    database._closed = True


def test_unclean_startup_rebuilds_indexes_from_committed_heap(
    tmp_path: Path,
) -> None:
    with Database.open(tmp_path) as database:
        database.execute(
            "CREATE TABLE users (id INT PRIMARY KEY, name TEXT)"
        )
        database.execute("INSERT INTO users VALUES (1, 'A')")

    database = Database.open(tmp_path)
    database.execute("INSERT INTO users VALUES (2, 'B')")
    _crash_without_cleanup(database)
    relation_path(tmp_path, btree_relation(1)).unlink(missing_ok=True)

    with Database.open(tmp_path) as recovered:
        recovered.execute("ANALYZE users")
        assert recovered.execute(
            "SELECT name FROM users WHERE id = 2"
        ).rows == (("B",),)
