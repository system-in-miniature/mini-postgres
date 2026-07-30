"""Central outcome-based decision rule for teaching-scale HOT updates."""

from __future__ import annotations


def hot_eligible(
    *,
    same_heap_page: bool,
    old_index_keys: tuple[bytes, ...],
    new_index_keys: tuple[bytes, ...],
) -> bool:
    """Return whether an already-placed replacement may remain heap-only.

    PostgreSQL decides HOT eligibility before insertion from modified
    attributes and page space. MiniPostgres intentionally checks the actual
    placement and encoded index-key outcome so this helper preserves the
    existing teaching implementation's behavior exactly.
    """

    return same_heap_page and old_index_keys == new_index_keys
