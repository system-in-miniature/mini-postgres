"""Schema-directed encoding for persistent heap tuple versions."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from minipostgres.catalog.model import Schema
from minipostgres.errors import CatalogError, CorruptPage, RowTooLarge
from minipostgres.row import TID
from minipostgres.storage.slotted import MAX_SLOT_PAYLOAD
from minipostgres.types import DataType, Scalar

SYSTEM_XID = 1

_TUPLE_MAGIC = b"TUP1"
_TUPLE_VERSION = 1
_HAS_NEXT_TID = 1
_HEADER = struct.Struct(">4sBBHQQQIII")
_INT64 = struct.Struct(">q")
_FLOAT64 = struct.Struct(">d")
_TEXT_LENGTH = struct.Struct(">I")
_MAX_UINT64 = 2**64 - 1
_MAX_UINT32 = 2**32 - 1


@dataclass(frozen=True, slots=True)
class TupleVersion:
    """One physical row version and its future MVCC chain link."""

    xmin: int
    xmax: int
    next_tid: TID | None
    values: tuple[Scalar, ...]


def _schema_fingerprint(schema: Schema) -> int:
    payload = bytearray()
    for column in schema.columns:
        name = column.name.encode("utf-8")
        payload.extend(len(name).to_bytes(4, "big"))
        payload.extend(name)
        payload.extend(column.data_type.value.encode("ascii"))
        payload.extend(
            bytes(
                (
                    column.nullable,
                    column.primary_key,
                    column.unique,
                )
            )
        )
    return zlib.crc32(payload) & _MAX_UINT32


def _validate_uint(value: int, maximum: int, field: str) -> None:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{field} is outside the encoded integer domain")


class TupleCodec:
    """Encode and decode tuple versions against one immutable schema."""

    def __init__(self, schema: Schema) -> None:
        self._schema = schema
        self._schema_hash = _schema_fingerprint(schema)

    def encode(self, version: TupleVersion) -> bytes:
        """Encode a validated row with a fixed version header."""

        _validate_uint(version.xmin, _MAX_UINT64, "xmin")
        _validate_uint(version.xmax, _MAX_UINT64, "xmax")
        try:
            values = self._schema.validate_row(version.values)
        except CatalogError:
            raise

        flags = 0
        next_page = 0
        next_slot = 0
        if version.next_tid is not None:
            _validate_uint(version.next_tid.page_id, _MAX_UINT64, "next page")
            _validate_uint(version.next_tid.slot_id, _MAX_UINT32, "next slot")
            flags |= _HAS_NEXT_TID
            next_page = version.next_tid.page_id
            next_slot = version.next_tid.slot_id

        null_bitmap = bytearray((len(values) + 7) // 8)
        payload = bytearray(null_bitmap)
        for index, (column, value) in enumerate(
            zip(self._schema.columns, values, strict=True)
        ):
            if value is None:
                payload[index // 8] |= 1 << (index % 8)
                continue
            if column.data_type is DataType.INT64:
                assert type(value) is int
                payload.extend(_INT64.pack(value))
            elif column.data_type is DataType.FLOAT64:
                assert type(value) is float
                payload.extend(_FLOAT64.pack(value))
            elif column.data_type is DataType.BOOLEAN:
                assert type(value) is bool
                payload.append(1 if value else 0)
            else:
                assert type(value) is str
                encoded_text = value.encode("utf-8")
                if len(encoded_text) > _MAX_UINT32:
                    raise RowTooLarge("TEXT value exceeds encoded length limit")
                payload.extend(_TEXT_LENGTH.pack(len(encoded_text)))
                payload.extend(encoded_text)

        encoded = _HEADER.pack(
            _TUPLE_MAGIC,
            _TUPLE_VERSION,
            flags,
            len(values),
            version.xmin,
            version.xmax,
            next_page,
            next_slot,
            self._schema_hash,
            len(payload),
        ) + bytes(payload)
        if len(encoded) > MAX_SLOT_PAYLOAD:
            raise RowTooLarge(
                f"encoded tuple is {len(encoded)} bytes; "
                f"maximum is {MAX_SLOT_PAYLOAD}"
            )
        return encoded

    def decode(self, encoded: bytes) -> TupleVersion:
        """Decode one tuple and reject any non-canonical or corrupt payload."""

        if len(encoded) < _HEADER.size:
            raise CorruptPage("truncated tuple header")
        (
            magic,
            version,
            flags,
            column_count,
            xmin,
            xmax,
            next_page,
            next_slot,
            schema_hash,
            payload_length,
        ) = _HEADER.unpack_from(encoded)
        if magic != _TUPLE_MAGIC or version != _TUPLE_VERSION:
            raise CorruptPage("unsupported tuple format")
        if flags & ~_HAS_NEXT_TID:
            raise CorruptPage("invalid tuple flags")
        if column_count != len(self._schema.columns):
            raise CorruptPage("tuple schema column count does not match")
        if schema_hash != self._schema_hash:
            raise CorruptPage("tuple schema fingerprint does not match")
        if len(encoded) != _HEADER.size + payload_length:
            raise CorruptPage("tuple payload length does not match")

        bitmap_length = (column_count + 7) // 8
        if payload_length < bitmap_length:
            raise CorruptPage("truncated tuple null bitmap")
        payload = memoryview(encoded)[_HEADER.size:]
        bitmap = payload[:bitmap_length]
        cursor = bitmap_length
        values: list[Scalar] = []
        for index, column in enumerate(self._schema.columns):
            if bitmap[index // 8] & (1 << (index % 8)):
                values.append(None)
                continue
            if column.data_type is DataType.INT64:
                end = self._require_bytes(payload, cursor, _INT64.size)
                value = _INT64.unpack_from(payload, cursor)[0]
                cursor = end
            elif column.data_type is DataType.FLOAT64:
                end = self._require_bytes(payload, cursor, _FLOAT64.size)
                value = _FLOAT64.unpack_from(payload, cursor)[0]
                cursor = end
            elif column.data_type is DataType.BOOLEAN:
                if cursor >= len(payload):
                    raise CorruptPage("truncated boolean value")
                boolean = int(payload[cursor])
                cursor += 1
                if boolean not in (0, 1):
                    raise CorruptPage("invalid boolean value")
                value = boolean == 1
            else:
                end = self._require_bytes(payload, cursor, _TEXT_LENGTH.size)
                raw_length = _TEXT_LENGTH.unpack_from(payload, cursor)[0]
                cursor = end
                end = cursor + raw_length
                if end > len(payload):
                    raise CorruptPage("truncated TEXT value")
                try:
                    value = bytes(payload[cursor:end]).decode("utf-8")
                except UnicodeDecodeError as error:
                    raise CorruptPage("invalid UTF-8 TEXT value") from error
                cursor = end
            values.append(value)
        if cursor != len(payload):
            raise CorruptPage("tuple payload has trailing bytes")

        if flags & _HAS_NEXT_TID:
            next_tid = TID(next_page, next_slot)
        else:
            if next_page != 0 or next_slot != 0:
                raise CorruptPage("tuple has hidden next-TID fields")
            next_tid = None
        result = TupleVersion(xmin, xmax, next_tid, tuple(values))
        try:
            self._schema.validate_row(result.values)
        except CatalogError as error:
            raise CorruptPage("tuple values violate the encoded schema") from error
        return result

    @staticmethod
    def _require_bytes(
        payload: memoryview,
        cursor: int,
        size: int,
    ) -> int:
        end = cursor + size
        if end > len(payload):
            raise CorruptPage("truncated fixed-width tuple value")
        return end
