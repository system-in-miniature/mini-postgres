from __future__ import annotations

import pytest

from minipostgres.errors import TypeMismatch
from minipostgres.index.key import KeyCodec
from minipostgres.types import DataType


def test_key_codec_preserves_scalar_and_composite_order() -> None:
    codec = KeyCodec((DataType.INT64, DataType.TEXT))
    values = [(-2, "z"), (1, "a"), (1, "b"), (9, "")]

    assert sorted(values, key=codec.encode) == values


def test_key_codec_orders_text_prefixes_and_embedded_nul() -> None:
    codec = KeyCodec((DataType.TEXT,))
    values = [("",), ("a",), ("a\x00",), ("aa",), ("雪",)]

    assert sorted(values, key=codec.encode) == values


def test_unique_index_rejects_null_key_in_frozen_scope() -> None:
    codec = KeyCodec((DataType.INT64,))

    with pytest.raises(TypeMismatch, match="NULL index key"):
        codec.encode((None,))


def test_key_codec_rejects_wrong_arity_type_and_nan() -> None:
    codec = KeyCodec((DataType.INT64, DataType.FLOAT64))

    with pytest.raises(TypeMismatch, match="2 components"):
        codec.encode((1,))
    with pytest.raises(TypeMismatch, match="INT64"):
        codec.encode((True, 1.0))
    with pytest.raises(TypeMismatch, match="NaN"):
        codec.encode((1, float("nan")))

