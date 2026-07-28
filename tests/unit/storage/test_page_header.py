from __future__ import annotations

import pytest

from minipostgres.errors import CorruptPage, RowTooLarge
from minipostgres.storage.constants import PAGE_SIZE, PageKind
from minipostgres.storage.identifiers import (
    ForkKind,
    PageKey,
    RelationId,
    heap_page_key,
)
from minipostgres.storage.page import decode_page, encode_page


def test_page_round_trip_preserves_identity_lsn_and_payload() -> None:
    key = PageKey(RelationId(ForkKind.HEAP, 7), page_id=3)

    encoded = encode_page(key, PageKind.HEAP, page_lsn=91, body=b"abc")
    decoded = decode_page(key, encoded)

    assert len(encoded) == PAGE_SIZE == 8192
    assert decoded.key == key
    assert decoded.kind is PageKind.HEAP
    assert decoded.page_lsn == 91
    assert decoded.body == b"abc"


def test_page_checksum_detects_torn_page() -> None:
    key = heap_page_key(1, 0)
    encoded = bytearray(encode_page(key, PageKind.HEAP, 0, b"row"))
    encoded[-1] ^= 0xFF

    with pytest.raises(CorruptPage, match="checksum"):
        decode_page(key, bytes(encoded))


def test_page_identity_is_bound_to_relation_fork_and_page_number() -> None:
    encoded = encode_page(heap_page_key(1, 0), PageKind.HEAP, 0, b"row")

    for wrong_key in (
        heap_page_key(2, 0),
        heap_page_key(1, 1),
        PageKey(RelationId(ForkKind.BTREE, 1), 0),
    ):
        with pytest.raises(CorruptPage, match="identity"):
            decode_page(wrong_key, encoded)


def test_page_decoder_rejects_wrong_size_and_invalid_header_fields() -> None:
    key = heap_page_key(1, 0)
    encoded = encode_page(key, PageKind.HEAP, 0, b"row")

    with pytest.raises(CorruptPage, match="8192"):
        decode_page(key, encoded[:-1])

    damaged_magic = bytearray(encoded)
    damaged_magic[0] ^= 0xFF
    with pytest.raises(CorruptPage, match="magic"):
        decode_page(key, bytes(damaged_magic))


def test_page_body_and_identifiers_enforce_format_limits() -> None:
    key = heap_page_key(1, 0)

    with pytest.raises(RowTooLarge):
        encode_page(key, PageKind.HEAP, 0, b"x" * PAGE_SIZE)
    with pytest.raises(ValueError):
        heap_page_key(-1, 0)
    with pytest.raises(ValueError):
        heap_page_key(1, -1)
