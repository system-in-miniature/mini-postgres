from __future__ import annotations

from minipostgres.engine import Database
from minipostgres.index.key import KeyCodec
from minipostgres.transaction.model import IsolationLevel
from minipostgres.types import DataType


def test_vacuum_removes_dead_versions_and_stale_index_entries(tmp_path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT)")
        database.execute("INSERT INTO users VALUES (7, 'old')")
        database.execute("DELETE FROM users WHERE id = 7")
        access = database._accesses[1]
        heap = access._mvcc_heap()
        assert len(tuple(heap.scan_versions())) == 1

        result = database.execute("VACUUM users")

        assert result.command_tag == "VACUUM 1"
        assert result.maintenance is not None
        assert result.maintenance.dead_versions_removed == 1
        key = KeyCodec((DataType.INT64,)).encode((7,))
        assert access.indexes[0].tree.search(key) == ()
        assert tuple(heap.scan_versions()) == ()
        database.execute("INSERT INTO users VALUES (8, 'new')")
        assert database.execute("SELECT * FROM users").rows == ((8, "new"),)


def test_long_repeatable_snapshot_prevents_reclamation(tmp_path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT PRIMARY KEY, age INT)")
        database.execute("INSERT INTO users VALUES (1, 20)")
        reader = database.session(isolation=IsolationLevel.REPEATABLE_READ)
        reader.execute("BEGIN")
        assert reader.execute("SELECT age FROM users").rows == ((20,),)
        database.execute("UPDATE users SET age = 21 WHERE id = 1")

        assert (
            database.execute("VACUUM users").maintenance.dead_versions_removed
            == 0
        )
        reader.execute("COMMIT")
        assert (
            database.execute("VACUUM users").maintenance.dead_versions_removed
            >= 1
        )
