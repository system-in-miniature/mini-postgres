"""Decision rule for heap-only tuple updates."""

from __future__ import annotations

from collections.abc import Set


def hot_eligible(
    changed_column_ids: Set[int],
    indexed_column_ids: Set[int],
    source_free_bytes: int,
    encoded_tuple_bytes: int,
) -> bool:
    return (
        changed_column_ids.isdisjoint(indexed_column_ids)
        and encoded_tuple_bytes <= source_free_bytes
    )
