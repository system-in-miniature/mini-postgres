"""Stable identifiers for relation forks and their pages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

_MAX_UINT64 = 2**64 - 1


class ForkKind(IntEnum):
    """One independently stored physical relation fork."""

    HEAP = 1
    BTREE = 2


def _validate_uint64(value: int, field: str) -> None:
    if type(value) is not int or value < 0 or value > _MAX_UINT64:
        raise ValueError(f"{field} must be an unsigned 64-bit integer")


@dataclass(frozen=True, slots=True)
class RelationId:
    """The physical object and access-method family owning a page."""

    fork: ForkKind
    object_id: int

    def __post_init__(self) -> None:
        _validate_uint64(self.object_id, "object_id")


@dataclass(frozen=True, slots=True)
class PageKey:
    """A page number scoped by its owning physical relation."""

    relation: RelationId
    page_id: int

    def __post_init__(self) -> None:
        _validate_uint64(self.page_id, "page_id")


def heap_relation(table_id: int) -> RelationId:
    """Build the canonical physical identity for a heap relation."""

    return RelationId(ForkKind.HEAP, table_id)


def btree_relation(index_id: int) -> RelationId:
    """Build the canonical physical identity for a B+Tree relation."""

    return RelationId(ForkKind.BTREE, index_id)


def heap_page_key(table_id: int, page_id: int) -> PageKey:
    """Build the canonical page identity for a heap relation."""

    return PageKey(heap_relation(table_id), page_id)


def btree_page_key(index_id: int, page_id: int) -> PageKey:
    """Build the canonical page identity for a B+Tree relation."""

    return PageKey(btree_relation(index_id), page_id)
