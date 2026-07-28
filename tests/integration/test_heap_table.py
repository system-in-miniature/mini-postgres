from __future__ import annotations

from pathlib import Path

from minipostgres.catalog.model import Column, Schema, TableMetadata
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.heap import HeapTable
from minipostgres.types import DataType


def _users() -> TableMetadata:
    return TableMetadata(
        table_id=1,
        name="users",
        schema=Schema.create(
            (
                Column("id", DataType.INT64, nullable=False),
                Column("name", DataType.TEXT, nullable=False),
                Column("age", DataType.INT64),
            )
        ),
    )


def _open_heap(root: Path) -> tuple[DiskManager, BufferPool, HeapTable]:
    disk = DiskManager.open(root)
    pool = BufferPool(disk, frame_count=2)
    return disk, pool, HeapTable.open(pool, _users())


def test_heap_insert_fetch_scan_update_delete_and_restart(tmp_path: Path) -> None:
    disk, pool, heap = _open_heap(tmp_path)
    first = heap.insert((1, "A", 20))
    second = heap.insert((2, "B", 30))
    replacement = heap.replace(second, (2, "B", 31))
    assert replacement is not None
    assert heap.delete(first)
    pool.flush_all()
    disk.close()

    reopened_disk, reopened_pool, reopened = _open_heap(tmp_path)

    assert reopened.fetch(first) is None
    assert reopened.fetch(replacement) == (2, "B", 31)
    assert list(reopened.scan()) == [(replacement, (2, "B", 31))]
    reopened_pool.flush_all()
    reopened_disk.close()


def test_heap_repairs_stale_free_space_estimate(tmp_path: Path) -> None:
    _disk, _pool, heap = _open_heap(tmp_path)
    first = heap.insert((1, "x" * 7_500, 20))
    assert first.page_id == 0
    heap.free_space.record(page_id=0, free_bytes=8_000)

    second = heap.insert((2, "y" * 1_000, 30))

    assert second.page_id == 1
    assert heap.fetch(second) == (2, "y" * 1_000, 30)


def test_heap_tids_keep_stable_slots_after_delete_and_compaction(
    tmp_path: Path,
) -> None:
    _disk, _pool, heap = _open_heap(tmp_path)
    first = heap.insert((1, "A", 20))
    deleted = heap.insert((2, "B", 30))
    third = heap.insert((3, "C", 40))

    assert heap.delete(deleted)
    inserted = heap.insert((4, "D" * 2_000, 50))

    assert first.slot_id == 0
    assert third.slot_id == 2
    assert heap.fetch(first) == (1, "A", 20)
    assert heap.fetch(third) == (3, "C", 40)
    assert heap.fetch(inserted) == (4, "D" * 2_000, 50)


def test_heap_reuses_space_reclaimable_by_compaction_after_delete(
    tmp_path: Path,
) -> None:
    _disk, _pool, heap = _open_heap(tmp_path)
    deleted = heap.insert((1, "x" * 7_000, 20))
    assert deleted.page_id == 0
    assert heap.delete(deleted)

    replacement = heap.insert((2, "y" * 6_500, 30))

    assert replacement.page_id == 0
    assert heap.fetch(replacement) == (2, "y" * 6_500, 30)
