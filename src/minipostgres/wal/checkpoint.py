"""Sharp checkpoints: force WAL and dirty pages before advancing control."""

from __future__ import annotations

from collections.abc import Iterable

from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import RelationId
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
    clean_shutdown: bool = False,
) -> int:
    """Create a no-dirty-page checkpoint and publish it atomically."""

    wal.flush()
    buffer_pool.flush_all()
    for relation in sorted(
        set(relations),
        key=lambda item: (int(item.fork), item.object_id),
    ):
        disk.sync_relation(relation)
    checkpoint_lsn = wal.append(0, CheckpointRecord(wal.end_lsn))
    wal.flush()
    control.store(ControlState(checkpoint_lsn, clean_shutdown))
    return checkpoint_lsn
