from __future__ import annotations

from pathlib import Path

from minipostgres.catalog.catalog import Catalog
from minipostgres.engine import Database
from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.heap import HeapTable
from minipostgres.storage.identifiers import btree_relation, heap_relation


def test_phase_b_storage_acceptance(tmp_path: Path) -> None:
    with Database.open(tmp_path, buffer_frames=3) as database:
        database.execute("CREATE TABLE events (id INT, payload TEXT)")
        for start in range(0, 500, 50):
            values = ", ".join(
                f"({value}, '{'x' * 100}')"
                for value in range(start, start + 50)
            )
            database.execute(f"INSERT INTO events VALUES {values}")
        database.execute("CREATE UNIQUE INDEX events_id ON events (id)")
        database.execute("DELETE FROM events WHERE id < 10")
        expected = database.execute(
            "SELECT id, payload FROM events ORDER BY id"
        ).rows

    with Database.open(tmp_path, buffer_frames=2) as reopened:
        assert reopened.execute(
            "SELECT id, payload FROM events ORDER BY id"
        ).rows == expected

    catalog = Catalog.open(tmp_path)
    table = catalog.table("events")
    index = catalog.index("events_id")
    disk = DiskManager.open(tmp_path)
    pool = BufferPool(disk, frame_count=2)
    heap = HeapTable.open(pool, table)
    tree = BTree.open(pool, index.index_id)
    codec = KeyCodec(
        tuple(
            table.schema.column(column_id).data_type
            for column_id in index.column_ids
        )
    )
    expected_entries = sorted(
        (
            codec.encode(tuple(values[column_id] for column_id in index.column_ids)),
            tid,
        )
        for tid, values in heap.scan()
    )

    assert disk.page_count(heap_relation(table.table_id)) > 1
    assert disk.page_count(btree_relation(index.index_id)) > 2
    assert list(tree.range(b"", b"\xff" * 64)) == expected_entries
    for key, tid in expected_entries:
        assert tid in tree.search(key)


def test_executor_has_no_direct_disk_or_collection_bypass() -> None:
    executor_root = Path("src/minipostgres/executor")
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(executor_root.glob("*.py"))
        if path.name != "memory.py"
    )

    assert "DiskManager" not in sources
    assert ".read_page(" not in sources
    assert "._slots" not in sources
