"""REDO full-page images and reconstruct transaction outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from minipostgres.errors import CorruptPage
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.page import decode_page
from minipostgres.transaction.status import (
    TransactionStatus,
    TransactionStatusTable,
)
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import (
    AbortRecord,
    BeginRecord,
    CommitRecord,
    HeapPageImagesRecord,
)


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    statuses: TransactionStatusTable
    next_xid: int
    redone_pages: int


def recover(
    wal: WalManager,
    disk: DiskManager,
    *,
    start_lsn: int = 0,
) -> RecoveryResult:
    statuses = TransactionStatusTable()
    begun: set[int] = set()
    maximum_xid = 1
    redone = 0
    for entry in wal.scan(start_lsn):
        maximum_xid = max(maximum_xid, entry.xid)
        record = entry.record
        if isinstance(record, BeginRecord):
            begun.add(entry.xid)
        elif isinstance(record, CommitRecord):
            statuses.set(entry.xid, TransactionStatus.COMMITTED)
        elif isinstance(record, AbortRecord):
            statuses.set(entry.xid, TransactionStatus.ABORTED)
        elif isinstance(record, HeapPageImagesRecord):
            for key, image in record.images:
                decoded_image = decode_page(key, image)
                while disk.page_count(key.relation) <= key.page_id:
                    disk.allocate_page(key.relation, decoded_image.kind)
                needs_redo = False
                try:
                    current = decode_page(key, disk.read_page(key))
                    needs_redo = current.page_lsn < decoded_image.page_lsn
                except CorruptPage:
                    needs_redo = True
                if needs_redo:
                    disk.write_page(key, image)
                    redone += 1
    for xid in begun:
        if statuses.get(xid) is TransactionStatus.IN_PROGRESS:
            statuses.set(xid, TransactionStatus.ABORTED)
    return RecoveryResult(statuses, maximum_xid + 1, redone)
