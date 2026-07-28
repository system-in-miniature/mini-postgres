from __future__ import annotations

import pytest

from minipostgres.catalog.model import Column, Schema
from minipostgres.errors import CorruptPage, RowTooLarge
from minipostgres.row import TID
from minipostgres.storage.tuple import SYSTEM_XID, TupleCodec, TupleVersion
from minipostgres.types import DataType


@pytest.fixture
def schema() -> Schema:
    return Schema.create(
        (
            Column("id", DataType.INT64, nullable=False),
            Column("score", DataType.FLOAT64),
            Column("active", DataType.BOOLEAN),
            Column("name", DataType.TEXT),
            Column("note", DataType.TEXT),
        )
    )


def test_tuple_codec_preserves_nulls_unicode_and_version_header(
    schema: Schema,
) -> None:
    version = TupleVersion(
        xmin=SYSTEM_XID,
        xmax=9,
        next_tid=TID(7, 3),
        values=(7, 1.5, True, "雪", None),
    )

    encoded = TupleCodec(schema).encode(version)

    assert TupleCodec(schema).decode(encoded) == version


def test_tuple_codec_rejects_wrong_schema_and_truncated_payload(
    schema: Schema,
) -> None:
    encoded = TupleCodec(schema).encode(
        TupleVersion(SYSTEM_XID, 0, None, (7, 1.5, False, "Ada", None))
    )
    other_schema = Schema.create(
        (
            Column("id", DataType.INT64, nullable=False),
            Column("score", DataType.FLOAT64),
            Column("active", DataType.BOOLEAN),
            Column("renamed", DataType.TEXT),
            Column("note", DataType.TEXT),
        )
    )

    with pytest.raises(CorruptPage, match="schema"):
        TupleCodec(other_schema).decode(encoded)
    with pytest.raises(CorruptPage, match=r"truncated|length"):
        TupleCodec(schema).decode(encoded[:-1])


def test_tuple_codec_rejects_invalid_boolean_and_trailing_bytes(
    schema: Schema,
) -> None:
    encoded = bytearray(
        TupleCodec(schema).encode(
            TupleVersion(SYSTEM_XID, 0, None, (7, 1.5, True, "Ada", None))
        )
    )
    # Fixed header (44), one-byte null bitmap, INT64, FLOAT64, then BOOLEAN.
    encoded[61] = 2

    with pytest.raises(CorruptPage, match="boolean"):
        TupleCodec(schema).decode(bytes(encoded))
    with pytest.raises(CorruptPage, match="length"):
        TupleCodec(schema).decode(bytes(encoded) + b"\x00")


def test_tuple_codec_rejects_a_value_larger_than_one_slot(schema: Schema) -> None:
    huge = "x" * 9_000

    with pytest.raises(RowTooLarge):
        TupleCodec(schema).encode(
            TupleVersion(SYSTEM_XID, 0, None, (7, 1.5, True, huge, None))
        )
