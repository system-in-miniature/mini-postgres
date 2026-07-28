from __future__ import annotations

import pytest

from minipostgres.errors import CorruptPage
from minipostgres.storage.slotted import SlottedPage


def test_compaction_moves_bytes_without_renumbering_live_slots() -> None:
    page = SlottedPage.empty(page_id=0)
    first = page.insert(b"a" * 100)
    second = page.insert(b"b" * 100)
    third = page.insert(b"c" * 100)

    page.delete(second)
    page.compact()

    assert (first, third) == (0, 2)
    assert page.read(first) == b"a" * 100
    assert page.read(third) == b"c" * 100
    assert page.live_slots() == (0, 2)


def test_insertion_reuses_a_dead_slot_without_changing_other_slot_ids() -> None:
    page = SlottedPage.empty(page_id=4)
    first = page.insert(b"first")
    deleted = page.insert(b"deleted")
    third = page.insert(b"third")
    page.delete(deleted)

    reused = page.insert(b"replacement")

    assert reused == deleted
    assert (first, third) == (0, 2)
    assert page.read(reused) == b"replacement"


def test_slotted_body_round_trip_preserves_dead_and_live_slots() -> None:
    page = SlottedPage.empty(page_id=8)
    page.insert(b"first")
    deleted = page.insert(b"deleted")
    page.insert(b"third")
    page.delete(deleted)

    restored = SlottedPage.from_body(page_id=8, body=page.to_body())

    assert restored.live_slots() == (0, 2)
    assert restored.read(0) == b"first"
    assert restored.read(2) == b"third"
    with pytest.raises(KeyError):
        restored.read(1)


def test_slotted_body_decoder_rejects_overlapping_extents() -> None:
    page = SlottedPage.empty(page_id=0)
    page.insert(b"first")
    page.insert(b"second")
    encoded = bytearray(page.to_body())

    # Copy slot zero's extent descriptor over slot one.
    encoded[20:28] = encoded[12:20]

    with pytest.raises(CorruptPage, match="overlap"):
        SlottedPage.from_body(page_id=0, body=bytes(encoded))
