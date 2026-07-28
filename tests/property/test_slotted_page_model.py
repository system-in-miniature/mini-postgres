from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from minipostgres.errors import PageFull
from minipostgres.storage.slotted import SlottedPage


@given(st.lists(st.binary(min_size=0, max_size=128), max_size=40))
def test_slotted_page_matches_stable_slot_reference(values: list[bytes]) -> None:
    page = SlottedPage.empty(page_id=0)
    model: dict[int, bytes] = {}

    for value in values:
        try:
            slot = page.insert(value)
        except PageFull:
            break
        model[slot] = value

    assert {slot: page.read(slot) for slot in page.live_slots()} == model
    restored = SlottedPage.from_body(page_id=0, body=page.to_body())
    assert {slot: restored.read(slot) for slot in restored.live_slots()} == model
