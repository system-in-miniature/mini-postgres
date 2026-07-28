"""Order-preserving composite key encoding for the frozen B+Tree subset."""

from __future__ import annotations

import math
import struct

from minipostgres.errors import TypeMismatch
from minipostgres.types import DataType, Scalar, validate_int64

_INT_TAG = 1
_FLOAT_TAG = 2
_BOOLEAN_TAG = 3
_TEXT_TAG = 4
_SIGN_BIT = 1 << 63
_UINT64_MASK = 2**64 - 1
_FLOAT64 = struct.Struct(">d")
_UINT64 = struct.Struct(">Q")


class KeyCodec:
    """Encode fixed-schema scalar tuples so byte order equals SQL value order."""

    def __init__(self, data_types: tuple[DataType, ...]) -> None:
        if not data_types:
            raise ValueError("an index key must contain at least one component")
        self.data_types = data_types

    def encode(self, values: tuple[Scalar, ...]) -> bytes:
        """Encode a non-null key with one unambiguous component per column."""

        if len(values) != len(self.data_types):
            raise TypeMismatch(
                f"index key requires {len(self.data_types)} components"
            )
        encoded = bytearray()
        for data_type, value in zip(self.data_types, values, strict=True):
            if value is None:
                raise TypeMismatch("NULL index key is outside the frozen scope")
            if data_type is DataType.INT64:
                if type(value) is not int:
                    raise TypeMismatch("index key component must be INT64")
                integer = validate_int64(value)
                encoded.append(_INT_TAG)
                encoded.extend((integer + _SIGN_BIT).to_bytes(8, "big"))
            elif data_type is DataType.FLOAT64:
                if type(value) is not float:
                    raise TypeMismatch("index key component must be FLOAT64")
                if math.isnan(value):
                    raise TypeMismatch("NaN index keys are outside the frozen scope")
                bits = _UINT64.unpack(_FLOAT64.pack(value))[0]
                sortable = (
                    (~bits & _UINT64_MASK)
                    if bits & _SIGN_BIT
                    else bits ^ _SIGN_BIT
                )
                encoded.append(_FLOAT_TAG)
                encoded.extend(_UINT64.pack(sortable))
            elif data_type is DataType.BOOLEAN:
                if type(value) is not bool:
                    raise TypeMismatch("index key component must be BOOLEAN")
                encoded.extend((_BOOLEAN_TAG, int(value)))
            else:
                if type(value) is not str:
                    raise TypeMismatch("index key component must be TEXT")
                encoded.append(_TEXT_TAG)
                for byte in value.encode("utf-8"):
                    if byte == 0:
                        encoded.extend((0, 255))
                    else:
                        encoded.append(byte)
                encoded.extend((0, 0))
        return bytes(encoded)
