from __future__ import annotations

import pytest

from minipostgres.storage.replacer import ClockReplacer


def test_clock_skips_pinned_and_gives_referenced_frame_second_chance() -> None:
    clock = ClockReplacer(frame_count=3)
    clock.mark_evictable(0, True)
    clock.mark_evictable(1, False)
    clock.mark_evictable(2, True)
    clock.record_access(0)

    assert clock.evict() == 2
    assert clock.evict() == 0


def test_clock_returns_none_when_every_frame_is_pinned() -> None:
    clock = ClockReplacer(frame_count=2)

    assert clock.evict() is None


def test_evicted_frame_must_be_registered_again_before_reuse() -> None:
    clock = ClockReplacer(frame_count=1)
    clock.mark_evictable(0, True)

    assert clock.evict() == 0
    assert clock.evict() is None
    clock.mark_evictable(0, True)
    assert clock.evict() == 0


def test_clock_rejects_invalid_capacity_and_frame_ids() -> None:
    with pytest.raises(ValueError):
        ClockReplacer(frame_count=0)

    clock = ClockReplacer(frame_count=2)
    with pytest.raises(IndexError):
        clock.record_access(2)
    with pytest.raises(IndexError):
        clock.mark_evictable(-1, True)
