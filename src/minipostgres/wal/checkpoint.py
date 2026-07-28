"""Sharp checkpoint ordering for the single-process runtime."""

from __future__ import annotations

from collections.abc import Iterable

from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import RelationId
from minipostgres.transaction.status import TransactionStatus
from minipostgres.wal.control_file import ControlFile, ControlState
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import CheckpointRecord


def sharp_checkpoint(
    wal: WalManager,
    buffer_pool: BufferPool,
    disk: DiskManager,
    relations: Iterable[RelationId],
    control: ControlFile,
    *,
    next_xid: int = 2,
    statuses: tuple[tuple[int, TransactionStatus], ...] = (),
    clean_shutdown: bool = False,
) -> int:
    wal.flush(wal.end_lsn)
    buffer_pool.flush_all()
    for relation in sorted(
        set(relations),
        key=lambda item: (int(item.fork), item.object_id),
    ):
        disk.sync_relation(relation)
    checkpoint_lsn = wal.append(0, CheckpointRecord(wal.end_lsn))
    wal.flush(wal.end_lsn)
    control.store(
        ControlState(
            checkpoint_lsn=checkpoint_lsn,
            clean_shutdown=clean_shutdown,
            next_xid=next_xid,
            statuses=statuses,
        )
    )
    return checkpoint_lsn
