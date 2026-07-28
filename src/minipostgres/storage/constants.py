"""Frozen constants for the MiniPostgres on-disk page format."""

from __future__ import annotations

from enum import IntEnum

PAGE_SIZE = 8192
PAGE_MAGIC = b"MPG1"
PAGE_FORMAT_VERSION = 1
PAGE_HEADER_SIZE = 44
PAGE_BODY_SIZE = PAGE_SIZE - PAGE_HEADER_SIZE


class PageKind(IntEnum):
    """The physical interpretation of one fixed-size page."""

    HEAP = 1
    BTREE_META = 2
    BTREE_INTERNAL = 3
    BTREE_LEAF = 4
