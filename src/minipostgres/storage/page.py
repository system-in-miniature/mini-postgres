"""Checksummed fixed-size page envelope."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from minipostgres.errors import CorruptPage, RowTooLarge
from minipostgres.storage.constants import (
    PAGE_FORMAT_VERSION,
    PAGE_MAGIC,
    PAGE_SIZE,
    PageKind,
)
from minipostgres.storage.identifiers import ForkKind, PageKey

# magic, version, page kind, fork kind, flags, object/page/LSN,
# lower/upper/special/reserved, checksum
_HEADER = struct.Struct(">4sBBBBQQQHHHHI")
_CHECKSUM_OFFSET = _HEADER.size - struct.calcsize(">I")
_MAX_BODY_SIZE = PAGE_SIZE - _HEADER.size
_MAX_UINT64 = 2**64 - 1


@dataclass(frozen=True, slots=True)
class DecodedPage:
    """Validated logical fields from an encoded page."""

    key: PageKey
    kind: PageKind
    page_lsn: int
    lower: int
    upper: int
    special: int
    body: bytes


def _checked_lsn(page_lsn: int) -> int:
    if type(page_lsn) is not int or page_lsn < 0 or page_lsn > _MAX_UINT64:
        raise ValueError("page_lsn must be an unsigned 64-bit integer")
    return page_lsn


def _page_bytes_with_checksum_zeroed(encoded: bytes) -> bytearray:
    checksum_input = bytearray(encoded)
    checksum_input[_CHECKSUM_OFFSET : _CHECKSUM_OFFSET + 4] = b"\x00" * 4
    return checksum_input


def encode_page(
    key: PageKey,
    kind: PageKind,
    page_lsn: int,
    body: bytes,
) -> bytes:
    """Encode one page and bind its checksum to identity and zero padding."""

    _checked_lsn(page_lsn)
    if len(body) > _MAX_BODY_SIZE:
        raise RowTooLarge(
            f"page body is {len(body)} bytes; maximum is {_MAX_BODY_SIZE}"
        )

    lower = _HEADER.size
    upper = lower + len(body)
    special = PAGE_SIZE
    header = _HEADER.pack(
        PAGE_MAGIC,
        PAGE_FORMAT_VERSION,
        int(kind),
        int(key.relation.fork),
        0,
        key.relation.object_id,
        key.page_id,
        page_lsn,
        lower,
        upper,
        special,
        0,
        0,
    )
    encoded = header + body + b"\x00" * (PAGE_SIZE - len(header) - len(body))
    checksum = zlib.crc32(encoded) & 0xFFFFFFFF
    mutable = bytearray(encoded)
    mutable[_CHECKSUM_OFFSET : _CHECKSUM_OFFSET + 4] = checksum.to_bytes(4, "big")
    return bytes(mutable)


def decode_page(expected_key: PageKey, encoded: bytes) -> DecodedPage:
    """Validate and decode one page expected at a specific physical address."""

    if len(encoded) != PAGE_SIZE:
        raise CorruptPage(
            f"page must contain exactly {PAGE_SIZE} bytes, got {len(encoded)}"
        )
    (
        magic,
        version,
        kind_value,
        fork_value,
        flags,
        object_id,
        page_id,
        page_lsn,
        lower,
        upper,
        special,
        reserved,
        stored_checksum,
    ) = _HEADER.unpack_from(encoded)
    if magic != PAGE_MAGIC:
        raise CorruptPage("invalid page magic")
    if version != PAGE_FORMAT_VERSION:
        raise CorruptPage(f"unsupported page format version: {version}")
    try:
        kind = PageKind(kind_value)
        fork = ForkKind(fork_value)
    except ValueError as error:
        raise CorruptPage("invalid page or fork kind") from error
    if flags != 0 or reserved != 0:
        raise CorruptPage("reserved page header fields are not zero")
    if (
        fork is not expected_key.relation.fork
        or object_id != expected_key.relation.object_id
        or page_id != expected_key.page_id
    ):
        raise CorruptPage("page identity does not match requested page")
    if not (_HEADER.size <= lower <= upper <= special <= PAGE_SIZE):
        raise CorruptPage("invalid page bounds")

    checksum_input = _page_bytes_with_checksum_zeroed(encoded)
    actual_checksum = zlib.crc32(checksum_input) & 0xFFFFFFFF
    if stored_checksum != actual_checksum:
        raise CorruptPage("page checksum mismatch")

    return DecodedPage(
        key=expected_key,
        kind=kind,
        page_lsn=page_lsn,
        lower=lower,
        upper=upper,
        special=special,
        body=encoded[_HEADER.size:upper],
    )
