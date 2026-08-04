from collections.abc import Iterator
from pathlib import Path

from pytest import MonkeyPatch

from minipostgres.engine import Database
from minipostgres.row import TID
from minipostgres.storage.disk import relation_path
from minipostgres.storage.heap import HeapTable
from minipostgres.storage.identifiers import btree_relation
from minipostgres.storage.tuple import TupleVersion


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


def test_unclean_index_rebuild_scans_each_heap_once(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    database = Database.open(tmp_path)
    database.execute("CREATE TABLE events (id INT PRIMARY KEY, payload INT)")
    for row_id in range(4):
        database.execute(f"INSERT INTO events VALUES ({row_id}, {row_id})")
    database.execute("UPDATE events SET payload = 99 WHERE id = 1")
    _crash_without_cleanup(database)

    scans = 0
    original_scan_versions = HeapTable.scan_versions

    def counted_scan_versions(
        self: HeapTable,
    ) -> Iterator[tuple[TID, TupleVersion]]:
        nonlocal scans
        scans += 1
        return original_scan_versions(self)

    monkeypatch.setattr(HeapTable, "scan_versions", counted_scan_versions)

    with Database.open(tmp_path) as recovered:
        startup_scans = scans
        assert recovered.execute("SELECT COUNT(*) FROM events").rows == ((4,),)
        table_id = recovered.catalog.table("events").table_id
        access = recovered._accesses[table_id]
        binding = access.indexes[0]
        root_tids = binding.tree.search(binding.codec.encode((1,)))
        assert len(root_tids) == 1
        resolved = access._mvcc_heap().resolve_globally_live(
            root_tids[0],
            0,
            recovered._transactions.statuses,
        )
        assert resolved is not None
        assert resolved[1] == (1, 99)

    assert startup_scans == 1
