"""Persistent body codecs for MiniPostgres B+Tree pages."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from itertools import pairwise

from minipostgres.errors import CorruptPage, PageFull
from minipostgres.row import TID
from minipostgres.storage.constants import PAGE_BODY_SIZE

_META_MAGIC = b"BTM1"
_INTERNAL_MAGIC = b"BTI1"
_LEAF_MAGIC = b"BTL1"
_NO_PAGE = 2**64 - 1
_MAX_UINT64 = _NO_PAGE
_MAX_UINT32 = 2**32 - 1
_META = struct.Struct(">4sQH2x")
_INTERNAL = struct.Struct(">4sH2xQ")
_LEAF = struct.Struct(">4sQQH2x")
_KEY_LENGTH = struct.Struct(">H")
_CHILD = struct.Struct(">Q")
_TID = struct.Struct(">QI")


@dataclass(frozen=True, slots=True)
class MetaPage:
    root_page_id: int
    height: int


@dataclass(frozen=True, slots=True)
class InternalPage:
    keys: tuple[bytes, ...]
    children: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LeafEntry:
    key: bytes
    tid: TID


@dataclass(frozen=True, slots=True)
class LeafPage:
    entries: tuple[LeafEntry, ...]
    left_sibling: int | None
    right_sibling: int | None


def encode_meta(page: MetaPage) -> bytes:
    """Encode root identity and current tree height."""

    _page_id(page.root_page_id, "root page")
    if type(page.height) is not int or page.height <= 0 or page.height > 65535:
        raise CorruptPage("invalid BTree height")
    return _META.pack(_META_MAGIC, page.root_page_id, page.height)


def decode_meta(body: bytes) -> MetaPage:
    if len(body) != _META.size:
        raise CorruptPage("truncated or trailing BTree metapage")
    magic, root_page_id, height = _META.unpack(body)
    if magic != _META_MAGIC:
        raise CorruptPage("invalid BTree metapage magic")
    page = MetaPage(root_page_id, height)
    encode_meta(page)
    return page


def encode_internal(page: InternalPage) -> bytes:
    """Encode ordered separators and their one-more child pointers."""

    if len(page.children) != len(page.keys) + 1:
        raise CorruptPage("internal page children must outnumber keys by one")
    if not page.children:
        raise CorruptPage("internal page has no children")
    if any(left > right for left, right in pairwise(page.keys)):
        raise CorruptPage("internal separator keys are not sorted")
    encoded = bytearray(
        _INTERNAL.pack(
            _INTERNAL_MAGIC,
            len(page.keys),
            _page_id(page.children[0], "child page"),
        )
    )
    for key, child in zip(page.keys, page.children[1:], strict=True):
        _append_key(encoded, key)
        encoded.extend(_CHILD.pack(_page_id(child, "child page")))
    return _bounded(encoded)


def decode_internal(body: bytes) -> InternalPage:
    if len(body) < _INTERNAL.size:
        raise CorruptPage("truncated BTree internal page")
    magic, key_count, first_child = _INTERNAL.unpack_from(body)
    if magic != _INTERNAL_MAGIC:
        raise CorruptPage("invalid BTree internal page magic")
    cursor = _INTERNAL.size
    keys: list[bytes] = []
    children = [first_child]
    for _ in range(key_count):
        key, cursor = _read_key(body, cursor)
        end = cursor + _CHILD.size
        if end > len(body):
            raise CorruptPage("truncated BTree child pointer")
        children.append(_CHILD.unpack_from(body, cursor)[0])
        keys.append(key)
        cursor = end
    if cursor != len(body):
        raise CorruptPage("BTree internal page has trailing bytes")
    page = InternalPage(tuple(keys), tuple(children))
    encode_internal(page)
    return page


def encode_leaf(page: LeafPage) -> bytes:
    """Encode sorted key/TID pairs and sibling links."""

    ordered = tuple(_entry_order(entry) for entry in page.entries)
    if any(left > right for left, right in pairwise(ordered)):
        raise CorruptPage("leaf entries are not sorted")
    encoded = bytearray(
        _LEAF.pack(
            _LEAF_MAGIC,
            _encode_sibling(page.left_sibling),
            _encode_sibling(page.right_sibling),
            len(page.entries),
        )
    )
    for entry in page.entries:
        _append_key(encoded, entry.key)
        _page_id(entry.tid.page_id, "TID page")
        if entry.tid.slot_id > _MAX_UINT32:
            raise CorruptPage("TID slot is outside the index format")
        encoded.extend(_TID.pack(entry.tid.page_id, entry.tid.slot_id))
    return _bounded(encoded)


def decode_leaf(body: bytes) -> LeafPage:
    if len(body) < _LEAF.size:
        raise CorruptPage("truncated BTree leaf page")
    magic, left, right, entry_count = _LEAF.unpack_from(body)
    if magic != _LEAF_MAGIC:
        raise CorruptPage("invalid BTree leaf page magic")
    cursor = _LEAF.size
    entries: list[LeafEntry] = []
    for _ in range(entry_count):
        key, cursor = _read_key(body, cursor)
        end = cursor + _TID.size
        if end > len(body):
            raise CorruptPage("truncated BTree leaf TID")
        page_id, slot_id = _TID.unpack_from(body, cursor)
        entries.append(LeafEntry(key, TID(page_id, slot_id)))
        cursor = end
    if cursor != len(body):
        raise CorruptPage("BTree leaf page has trailing bytes")
    page = LeafPage(
        tuple(entries),
        _decode_sibling(left),
        _decode_sibling(right),
    )
    encode_leaf(page)
    return page


def _entry_order(entry: LeafEntry) -> tuple[bytes, int, int]:
    return entry.key, entry.tid.page_id, entry.tid.slot_id


def _append_key(encoded: bytearray, key: bytes) -> None:
    if len(key) > 65535:
        raise PageFull("BTree key exceeds the page key-length field")
    encoded.extend(_KEY_LENGTH.pack(len(key)))
    encoded.extend(key)


def _read_key(body: bytes, cursor: int) -> tuple[bytes, int]:
    length_end = cursor + _KEY_LENGTH.size
    if length_end > len(body):
        raise CorruptPage("truncated BTree key length")
    length = _KEY_LENGTH.unpack_from(body, cursor)[0]
    end = length_end + length
    if end > len(body):
        raise CorruptPage("truncated BTree key")
    return body[length_end:end], end


def _page_id(value: int, field: str) -> int:
    if type(value) is not int or value < 0 or value >= _NO_PAGE:
        raise CorruptPage(f"invalid {field}")
    return value


def _encode_sibling(page_id: int | None) -> int:
    return _NO_PAGE if page_id is None else _page_id(page_id, "sibling page")


def _decode_sibling(encoded: int) -> int | None:
    return None if encoded == _NO_PAGE else encoded


def _bounded(encoded: bytearray) -> bytes:
    if len(encoded) > PAGE_BODY_SIZE:
        raise PageFull(
            f"BTree page body is {len(encoded)} bytes; "
            f"maximum is {PAGE_BODY_SIZE}"
        )
    return bytes(encoded)
