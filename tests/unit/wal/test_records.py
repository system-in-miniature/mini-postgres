from __future__ import annotations

from minipostgres.storage.constants import PAGE_SIZE
from minipostgres.storage.identifiers import PageKey, heap_relation
from minipostgres.wal.records import (
    AbortRecord,
    BeginRecord,
    CheckpointRecord,
    CommitRecord,
    HeapPageImagesRecord,
    decode_record,
    encode_record,
)


def test_wal_record_codec_round_trips_every_record_kind() -> None:
    key = PageKey(heap_relation(7), 3)
    records = (
        BeginRecord(),
        HeapPageImagesRecord(((key, b"x" * PAGE_SIZE),)),
        CommitRecord(),
        AbortRecord(),
        CheckpointRecord(41),
    )

    for record in records:
        encoded = encode_record(17, 9, record)
        decoded = decode_record(encoded)
        assert decoded.lsn == 17
        assert decoded.xid == 9
        assert decoded.record == record
        assert decoded.end_lsn == 17 + len(encoded)

