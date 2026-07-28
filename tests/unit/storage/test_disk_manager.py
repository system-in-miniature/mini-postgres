from __future__ import annotations

from pathlib import Path

import pytest

from minipostgres.errors import CorruptPage, DatabaseClosed
from minipostgres.storage.constants import PAGE_SIZE, PageKind
from minipostgres.storage.disk import DiskManager, relation_path
from minipostgres.storage.identifiers import heap_relation
from minipostgres.storage.page import encode_page


def test_disk_manager_allocates_reads_and_reopens_pages(tmp_path: Path) -> None:
    manager = DiskManager.open(tmp_path)
    relation = heap_relation(4)
    key = manager.allocate_page(relation)
    page = encode_page(key, PageKind.HEAP, 0, b"durable")

    manager.write_page(key, page)
    manager.sync_relation(relation)
    manager.close()
    reopened = DiskManager.open(tmp_path)

    assert reopened.read_page(key) == page
    assert reopened.page_count(relation) == 1
    reopened.close()


def test_disk_manager_rejects_short_relation_files(tmp_path: Path) -> None:
    relation = heap_relation(1)
    path = relation_path(tmp_path, relation)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"partial")

    with pytest.raises(CorruptPage, match="multiple of"):
        DiskManager.open(tmp_path).page_count(relation)


def test_disk_manager_validates_page_identity_before_write(tmp_path: Path) -> None:
    manager = DiskManager.open(tmp_path)
    relation = heap_relation(1)
    first = manager.allocate_page(relation)
    wrong = encode_page(
        manager.allocate_page(relation),
        PageKind.HEAP,
        0,
        b"wrong page",
    )

    with pytest.raises(CorruptPage, match="identity"):
        manager.write_page(first, wrong)
    assert relation_path(tmp_path, relation).stat().st_size == 2 * PAGE_SIZE


def test_disk_manager_close_is_idempotent_and_blocks_new_io(
    tmp_path: Path,
) -> None:
    manager = DiskManager.open(tmp_path)
    manager.close()
    manager.close()

    with pytest.raises(DatabaseClosed):
        manager.page_count(heap_relation(1))

