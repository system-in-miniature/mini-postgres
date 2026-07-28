from __future__ import annotations

from minipostgres.storage.buffer import BufferPool
from minipostgres.storage.constants import PageKind
from minipostgres.storage.disk import DiskManager
from minipostgres.storage.identifiers import heap_relation
from minipostgres.storage.page import decode_page, encode_page
from minipostgres.wal.checkpoint import sharp_checkpoint
from minipostgres.wal.control_file import ControlFile
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import CheckpointRecord


def test_sharp_checkpoint_flushes_wal_pages_and_control_metadata(tmp_path) -> None:
    disk = DiskManager.open(tmp_path)
    wal = WalManager.open(tmp_path / "wal.log")
    pool = BufferPool(disk, 2, wal_flush_gate=wal.flush)
    relation = heap_relation(4)
    with pool.new_page(relation, PageKind.HEAP) as guard:
        lsn = wal.end_lsn
        wal.append(3, CheckpointRecord(0))
        guard.replace_bytes(
            encode_page(guard.key, PageKind.HEAP, lsn, b"checkpointed")
        )
        guard.mark_dirty(lsn)
        key = guard.key
    control = ControlFile(tmp_path / "control")

    checkpoint_lsn = sharp_checkpoint(
        wal,
        pool,
        disk,
        (relation,),
        control,
        clean_shutdown=True,
    )

    assert control.load().checkpoint_lsn == checkpoint_lsn
    assert control.load().clean_shutdown
    assert decode_page(key, disk.read_page(key)).body == b"checkpointed"
    assert wal.flushed_lsn == wal.end_lsn
    wal.close()
    disk.close()
