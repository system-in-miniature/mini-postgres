from pathlib import Path

from minipostgres.engine import Database
from minipostgres.storage.constants import PAGE_SIZE
from minipostgres.storage.disk import relation_path
from minipostgres.storage.identifiers import heap_relation


def _crash_without_cleanup(database: Database) -> None:
    database._wal.close()
    database._disk.close()
    database._closed = True


def test_recovery_repairs_torn_post_checkpoint_heap_page(tmp_path: Path) -> None:
    with Database.open(tmp_path) as database:
        database.execute("CREATE TABLE users (id INT PRIMARY KEY)")
        database.execute("INSERT INTO users VALUES (1)")

    database = Database.open(tmp_path)
    database.execute("INSERT INTO users VALUES (2)")
    database._buffer_pool.flush_all()
    heap_path = relation_path(tmp_path, heap_relation(1))
    with heap_path.open("r+b") as stream:
        stream.seek(PAGE_SIZE // 2)
        stream.write(b"\xA5" * 128)
        stream.flush()
    _crash_without_cleanup(database)

    with Database.open(tmp_path) as recovered:
        assert recovered.execute(
            "SELECT id FROM users ORDER BY id"
        ).rows == ((1,), (2,))
