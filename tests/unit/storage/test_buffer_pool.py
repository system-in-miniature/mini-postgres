from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.errors import BufferPoolFull
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import heap_relation


def test_buffer_pool_reuses_a_resident_frame_and_counts_pins(
    tmp_path: Path,
) -> None:
    disk = DiskManager.open(tmp_path)
    key = disk.allocate_page(heap_relation(1))
    pool = BufferPool(disk, frame_count=1)

    first = pool.fetch_page(key)
    second = pool.fetch_page(key)

    assert pool.resident_page_count == 1
    assert pool.pin_count(key) == 2
    first.release()
    assert pool.pin_count(key) == 1
    second.release()
    assert pool.pin_count(key) == 0


def test_buffer_pool_cannot_evict_the_only_pinned_frame(tmp_path: Path) -> None:
    disk = DiskManager.open(tmp_path)
    relation = heap_relation(1)
    first_key = disk.allocate_page(relation)
    second_key = disk.allocate_page(relation)
    pool = BufferPool(disk, frame_count=1)

    with pool.fetch_page(first_key), pytest.raises(BufferPoolFull):
        pool.fetch_page(second_key)


def test_default_wal_gate_rejects_nonzero_dirty_lsn(tmp_path: Path) -> None:
    disk = DiskManager.open(tmp_path)
    key = disk.allocate_page(heap_relation(1))
    pool = BufferPool(disk, frame_count=1)

    with pool.fetch_page(key) as guard:
        guard.mark_dirty(1)

    with pytest.raises(RuntimeError, match="WAL"):
        pool.flush_page(key)
