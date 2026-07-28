from __future__ import annotations

from minipostgres.storage.constants import PageKind
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import heap_page_key, heap_relation
from minipostgres.storage.page import decode_page, encode_page
from minipostgres.transaction.status import TransactionStatus
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import (
    BeginRecord,
    CommitRecord,
    HeapPageImagesRecord,
)
from minipostgres.wal.recovery import recover


def test_recovery_redoes_newer_page_images_and_aborts_incomplete_xids(
    tmp_path,
) -> None:
    disk = DiskManager.open(tmp_path)
    key = disk.allocate_page(heap_relation(4), PageKind.HEAP)
    wal = WalManager.open(tmp_path / "wal.log")
    wal.append(7, BeginRecord())
    image_lsn = wal.end_lsn
    image = encode_page(key, PageKind.HEAP, image_lsn, b"committed")
    wal.append(7, HeapPageImagesRecord(((key, image),)))
    wal.append(7, CommitRecord())
    wal.append(8, BeginRecord())
    wal.flush()

    result = recover(wal, disk)

    assert result.statuses.get(7) is TransactionStatus.COMMITTED
    assert result.statuses.get(8) is TransactionStatus.ABORTED
    assert result.next_xid == 9
    assert decode_page(key, disk.read_page(key)).body == b"committed"
    wal.close()
    disk.close()


def test_recovery_allocates_a_missing_page_from_a_full_image(tmp_path) -> None:
    disk = DiskManager.open(tmp_path)
    key = heap_page_key(9, 0)
    wal = WalManager.open(tmp_path / "wal.log")
    wal.append(
        3,
        HeapPageImagesRecord(
            ((key, encode_page(key, PageKind.HEAP, 1, b"restored")),)
        ),
    )
    wal.flush()

    recover(wal, disk)

    assert decode_page(key, disk.read_page(key)).body == b"restored"
    wal.close()
    disk.close()


def test_recovery_reconstructs_old_statuses_when_redo_starts_later(
    tmp_path,
) -> None:
    disk = DiskManager.open(tmp_path)
    wal = WalManager.open(tmp_path / "wal.log")
    wal.append(11, BeginRecord())
    wal.append(11, CommitRecord())
    redo_start = wal.end_lsn
    wal.append(12, BeginRecord())
    wal.flush()

    result = recover(wal, disk, start_lsn=redo_start)

    assert result.statuses.get(11) is TransactionStatus.COMMITTED
    assert result.statuses.get(12) is TransactionStatus.ABORTED
    wal.close()
    disk.close()
