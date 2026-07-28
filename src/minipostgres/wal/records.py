"""Binary, checksummed WAL record codec."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from enum import IntEnum

from minipostgres.errors import CorruptWal
from minipostgres.storage.constants import PAGE_SIZE
from minipostgres.storage.identifiers import ForkKind, PageKey, RelationId

_MAGIC = b"MPWL"
_VERSION = 1
# magic, version, kind, flags, record length, lsn, xid, payload length, crc32
_HEADER = struct.Struct(">4sBBHIQQII")
_PAGE_IMAGE_HEADER = struct.Struct(">BQQ")
_COUNT = struct.Struct(">I")
_LSN = struct.Struct(">Q")
_CHECKSUM_OFFSET = _HEADER.size - 4


class RecordKind(IntEnum):
    BEGIN = 1
    HEAP_PAGE_IMAGES = 2
    COMMIT = 3
    ABORT = 4
    CHECKPOINT = 5


@dataclass(frozen=True, slots=True)
class BeginRecord:
    pass


@dataclass(frozen=True, slots=True)
class HeapPageImagesRecord:
    images: tuple[tuple[PageKey, bytes], ...]

    def __post_init__(self) -> None:
        if not self.images:
            raise ValueError("page-image record cannot be empty")
        if any(len(image) != PAGE_SIZE for _, image in self.images):
            raise ValueError("WAL page images must be complete physical pages")


@dataclass(frozen=True, slots=True)
class CommitRecord:
    pass


@dataclass(frozen=True, slots=True)
class AbortRecord:
    pass


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    redo_lsn: int


type WalRecord = (
    BeginRecord
    | HeapPageImagesRecord
    | CommitRecord
    | AbortRecord
    | CheckpointRecord
)


@dataclass(frozen=True, slots=True)
class DecodedWalRecord:
    lsn: int
    end_lsn: int
    xid: int
    record: WalRecord


def _kind(record: WalRecord) -> RecordKind:
    if isinstance(record, BeginRecord):
        return RecordKind.BEGIN
    if isinstance(record, HeapPageImagesRecord):
        return RecordKind.HEAP_PAGE_IMAGES
    if isinstance(record, CommitRecord):
        return RecordKind.COMMIT
    if isinstance(record, AbortRecord):
        return RecordKind.ABORT
    return RecordKind.CHECKPOINT


def _payload(record: WalRecord) -> bytes:
    if isinstance(record, HeapPageImagesRecord):
        chunks = [_COUNT.pack(len(record.images))]
        for key, image in record.images:
            chunks.append(
                _PAGE_IMAGE_HEADER.pack(
                    int(key.relation.fork),
                    key.relation.object_id,
                    key.page_id,
                )
            )
            chunks.append(image)
        return b"".join(chunks)
    if isinstance(record, CheckpointRecord):
        return _LSN.pack(record.redo_lsn)
    return b""


def encode_record(lsn: int, xid: int, record: WalRecord) -> bytes:
    payload = _payload(record)
    total_length = _HEADER.size + len(payload)
    header = _HEADER.pack(
        _MAGIC,
        _VERSION,
        int(_kind(record)),
        0,
        total_length,
        lsn,
        xid,
        len(payload),
        0,
    )
    encoded = bytearray(header + payload)
    checksum = zlib.crc32(encoded) & 0xFFFFFFFF
    encoded[_CHECKSUM_OFFSET : _CHECKSUM_OFFSET + 4] = checksum.to_bytes(4, "big")
    return bytes(encoded)


def record_length_from_header(header: bytes) -> int:
    if len(header) != _HEADER.size:
        raise CorruptWal("incomplete WAL header")
    magic, version, _, flags, total_length, _, _, payload_length, _ = (
        _HEADER.unpack(header)
    )
    if magic != _MAGIC or version != _VERSION or flags != 0:
        raise CorruptWal("invalid WAL header")
    if total_length != _HEADER.size + payload_length:
        raise CorruptWal("inconsistent WAL record length")
    return total_length


def decode_record(encoded: bytes) -> DecodedWalRecord:
    if len(encoded) < _HEADER.size:
        raise CorruptWal("incomplete WAL record")
    (
        magic,
        version,
        kind_value,
        flags,
        total_length,
        lsn,
        xid,
        payload_length,
        stored_checksum,
    ) = _HEADER.unpack_from(encoded)
    if magic != _MAGIC or version != _VERSION or flags != 0:
        raise CorruptWal("invalid WAL record header")
    if total_length != len(encoded) or payload_length != len(encoded) - _HEADER.size:
        raise CorruptWal("invalid WAL record length")
    checksum_input = bytearray(encoded)
    checksum_input[_CHECKSUM_OFFSET : _CHECKSUM_OFFSET + 4] = b"\x00" * 4
    if zlib.crc32(checksum_input) & 0xFFFFFFFF != stored_checksum:
        raise CorruptWal("WAL record checksum mismatch")
    try:
        kind = RecordKind(kind_value)
    except ValueError as error:
        raise CorruptWal("unknown WAL record kind") from error
    payload = encoded[_HEADER.size:]
    record = _decode_payload(kind, payload)
    return DecodedWalRecord(lsn, lsn + total_length, xid, record)


def _decode_payload(kind: RecordKind, payload: bytes) -> WalRecord:
    if kind is RecordKind.BEGIN:
        _require_empty(payload)
        return BeginRecord()
    if kind is RecordKind.COMMIT:
        _require_empty(payload)
        return CommitRecord()
    if kind is RecordKind.ABORT:
        _require_empty(payload)
        return AbortRecord()
    if kind is RecordKind.CHECKPOINT:
        if len(payload) != _LSN.size:
            raise CorruptWal("invalid checkpoint payload")
        return CheckpointRecord(_LSN.unpack(payload)[0])
    if len(payload) < _COUNT.size:
        raise CorruptWal("invalid page-image payload")
    count = _COUNT.unpack_from(payload)[0]
    cursor = _COUNT.size
    images: list[tuple[PageKey, bytes]] = []
    for _ in range(count):
        end_header = cursor + _PAGE_IMAGE_HEADER.size
        end_image = end_header + PAGE_SIZE
        if end_image > len(payload):
            raise CorruptWal("truncated page image")
        fork_value, object_id, page_id = _PAGE_IMAGE_HEADER.unpack(
            payload[cursor:end_header]
        )
        try:
            fork = ForkKind(fork_value)
        except ValueError as error:
            raise CorruptWal("invalid page-image fork") from error
        key = PageKey(RelationId(fork, object_id), page_id)
        images.append((key, payload[end_header:end_image]))
        cursor = end_image
    if cursor != len(payload) or not images:
        raise CorruptWal("invalid page-image payload length")
    return HeapPageImagesRecord(tuple(images))


def _require_empty(payload: bytes) -> None:
    if payload:
        raise CorruptWal("record kind requires an empty payload")


HEADER_SIZE = _HEADER.size
