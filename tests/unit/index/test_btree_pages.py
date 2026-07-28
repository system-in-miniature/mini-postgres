from __future__ import annotations

import pytest

from minipostgres.errors import CorruptPage
from minipostgres.index.pages import (
    InternalPage,
    LeafEntry,
    LeafPage,
    MetaPage,
    decode_internal,
    decode_leaf,
    decode_meta,
    encode_internal,
    encode_leaf,
    encode_meta,
)
from minipostgres.row import TID


def test_btree_page_codecs_round_trip_all_page_kinds() -> None:
    meta = MetaPage(root_page_id=7, height=3)
    internal = InternalPage(keys=(b"b", b"d"), children=(1, 2, 3))
    leaf = LeafPage(
        entries=(
            LeafEntry(b"a", TID(1, 2)),
            LeafEntry(b"b", TID(3, 4)),
        ),
        left_sibling=None,
        right_sibling=9,
    )

    assert decode_meta(encode_meta(meta)) == meta
    assert decode_internal(encode_internal(internal)) == internal
    assert decode_leaf(encode_leaf(leaf)) == leaf


def test_btree_page_decoders_reject_unsorted_and_truncated_payloads() -> None:
    leaf = LeafPage(
        entries=(
            LeafEntry(b"a", TID(0, 0)),
            LeafEntry(b"b", TID(0, 1)),
        ),
        left_sibling=None,
        right_sibling=None,
    )
    encoded = encode_leaf(leaf)

    with pytest.raises(CorruptPage, match="truncated"):
        decode_leaf(encoded[:-1])
    with pytest.raises(CorruptPage, match="sorted"):
        encode_leaf(
            LeafPage(
                entries=tuple(reversed(leaf.entries)),
                left_sibling=None,
                right_sibling=None,
            )
        )


def test_internal_page_requires_one_more_child_than_separator() -> None:
    with pytest.raises(CorruptPage, match="children"):
        encode_internal(InternalPage(keys=(b"a",), children=(1,)))

