from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.errors import DatabaseClosed
from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.constants import PageKind
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import heap_relation
from minipostgres.storage.page import decode_page, encode_page


def test_page_guard_unpins_and_records_dirty_lsn(tmp_path: Path) -> None:
    disk = DiskManager.open(tmp_path)
    key = disk.allocate_page(heap_relation(1))
    pool = BufferPool(disk, frame_count=1, wal_flush_gate=lambda _lsn: None)

    with pool.fetch_page(key) as guard:
        guard.replace_bytes(encode_page(key, PageKind.HEAP, 0, b"changed"))
        guard.mark_dirty(page_lsn=17)
        assert pool.pin_count(key) == 1
        assert decode_page(key, guard.page_bytes).page_lsn == 17

    assert pool.pin_count(key) == 0
    assert pool.frame(key).page_lsn == 17
    assert pool.frame(key).dirty is True


def test_page_guard_release_is_idempotent_and_blocks_late_mutation(
    tmp_path: Path,
) -> None:
    disk = DiskManager.open(tmp_path)
    key = disk.allocate_page(heap_relation(1))
    pool = BufferPool(disk, frame_count=1)
    guard = pool.fetch_page(key)

    guard.release()
    guard.release()

    assert pool.pin_count(key) == 0
    with pytest.raises(DatabaseClosed, match="guard"):
        guard.mark_dirty(0)


def test_page_guard_rejects_decreasing_lsn(tmp_path: Path) -> None:
    disk = DiskManager.open(tmp_path)
    key = disk.allocate_page(heap_relation(1))
    pool = BufferPool(disk, frame_count=1, wal_flush_gate=lambda _lsn: None)

    with pool.fetch_page(key) as guard:
        guard.mark_dirty(11)
        with pytest.raises(ValueError, match="decrease"):
            guard.mark_dirty(10)

