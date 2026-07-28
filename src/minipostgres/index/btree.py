"""Persistent page-based B+Tree insertion and point search."""

from __future__ import annotations

import threading
from bisect import bisect_left, bisect_right

from minipostgres.errors import CorruptPage, PageFull
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
from minipostgres.storage.buffer import BufferPool, PageGuard
from minipostgres.storage.constants import PAGE_BODY_SIZE, PageKind
from minipostgres.storage.identifiers import btree_page_key, btree_relation
from minipostgres.storage.page import decode_page, encode_page


class BTree:
    """A persistent sorted multimap from encoded keys to candidate heap TIDs."""

    def __init__(
        self,
        buffer_pool: BufferPool,
        index_id: int,
        root_page_id: int,
        height: int,
    ) -> None:
        self._pool = buffer_pool
        self.index_id = index_id
        self._relation = btree_relation(index_id)
        self._root_page_id = root_page_id
        self._height = height
        self._lock = threading.RLock()

    @classmethod
    def open(cls, buffer_pool: BufferPool, index_id: int) -> BTree:
        """Open an existing tree or initialize metapage plus empty leaf root."""

        relation = btree_relation(index_id)
        page_count = buffer_pool.page_count(relation)
        if page_count == 0:
            with buffer_pool.new_page(relation, PageKind.BTREE_META) as guard:
                if guard.key.page_id != 0:
                    raise CorruptPage("BTree metapage was not allocated at page zero")
            with buffer_pool.new_page(relation, PageKind.BTREE_LEAF) as guard:
                root_page_id = guard.key.page_id
                cls._replace_guard(
                    guard,
                    PageKind.BTREE_LEAF,
                    encode_leaf(LeafPage((), None, None)),
                )
            tree = cls(buffer_pool, index_id, root_page_id, 1)
            tree._write_meta()
            return tree

        meta_key = btree_page_key(index_id, 0)
        with buffer_pool.fetch_page(meta_key) as guard:
            decoded = decode_page(meta_key, guard.page_bytes)
            if decoded.kind is not PageKind.BTREE_META:
                raise CorruptPage("BTree page zero is not a metapage")
            meta = decode_meta(decoded.body)
        if meta.root_page_id >= page_count:
            raise CorruptPage("BTree metapage root is not allocated")
        return cls(
            buffer_pool,
            index_id,
            meta.root_page_id,
            meta.height,
        )

    @property
    def height(self) -> int:
        return self._height

    @property
    def root_page_id(self) -> int:
        return self._root_page_id

    def search(self, key: bytes) -> tuple[TID, ...]:
        """Return every exact-key candidate in deterministic TID order."""

        with self._lock:
            leaf_id, _ = self._find_leaf(key)
            leaf = self._read_leaf(leaf_id)
            while leaf.left_sibling is not None:
                left = self._read_leaf(leaf.left_sibling)
                if left.entries and left.entries[-1].key >= key:
                    leaf_id = leaf.left_sibling
                    leaf = left
                else:
                    break

            found: list[TID] = []
            while True:
                found.extend(entry.tid for entry in leaf.entries if entry.key == key)
                if (
                    leaf.right_sibling is None
                    or (leaf.entries and leaf.entries[-1].key > key)
                ):
                    break
                right = self._read_leaf(leaf.right_sibling)
                if right.entries and right.entries[0].key > key:
                    break
                leaf = right
            return tuple(
                sorted(
                    set(found),
                    key=lambda tid: (tid.page_id, tid.slot_id),
                )
            )

    def insert(self, key: bytes, tid: TID) -> None:
        """Insert one unique key/TID pair and recursively split overflow pages."""

        with self._lock:
            if tid in self.search(key):
                return
            leaf_id, path = self._find_leaf(key)
            leaf = self._read_leaf(leaf_id)
            entries = list(leaf.entries)
            entry = LeafEntry(key, tid)
            order = [(item.key, item.tid.page_id, item.tid.slot_id) for item in entries]
            position = bisect_left(order, (key, tid.page_id, tid.slot_id))
            entries.insert(position, entry)
            updated = LeafPage(
                tuple(entries),
                leaf.left_sibling,
                leaf.right_sibling,
            )
            try:
                body = encode_leaf(updated)
            except PageFull:
                separator, right_id = self._split_leaf(leaf_id, updated)
                self._propagate_split(path, leaf_id, separator, right_id)
            else:
                self._write_page(leaf_id, PageKind.BTREE_LEAF, body)

    def _find_leaf(self, key: bytes) -> tuple[int, list[tuple[int, int]]]:
        page_id = self._root_page_id
        path: list[tuple[int, int]] = []
        for _ in range(self._height - 1):
            internal = self._read_internal(page_id)
            child_index = bisect_right(internal.keys, key)
            path.append((page_id, child_index))
            page_id = internal.children[child_index]
        return page_id, path

    def _split_leaf(self, page_id: int, page: LeafPage) -> tuple[bytes, int]:
        split_at = self._leaf_split_position(page.entries)
        left_entries = page.entries[:split_at]
        right_entries = page.entries[split_at:]
        with self._pool.new_page(
            self._relation,
            PageKind.BTREE_LEAF,
        ) as right_guard:
            right_id = right_guard.key.page_id
            right = LeafPage(
                right_entries,
                left_sibling=page_id,
                right_sibling=page.right_sibling,
            )
            self._replace_guard(
                right_guard,
                PageKind.BTREE_LEAF,
                encode_leaf(right),
            )

        left = LeafPage(
            left_entries,
            left_sibling=page.left_sibling,
            right_sibling=right_id,
        )
        self._write_page(
            page_id,
            PageKind.BTREE_LEAF,
            encode_leaf(left),
        )
        if page.right_sibling is not None:
            old_right = self._read_leaf(page.right_sibling)
            linked = LeafPage(
                old_right.entries,
                left_sibling=right_id,
                right_sibling=old_right.right_sibling,
            )
            self._write_page(
                page.right_sibling,
                PageKind.BTREE_LEAF,
                encode_leaf(linked),
            )
        return right_entries[0].key, right_id

    def _propagate_split(
        self,
        path: list[tuple[int, int]],
        left_id: int,
        separator: bytes,
        right_id: int,
    ) -> None:
        while path:
            parent_id, child_index = path.pop()
            parent = self._read_internal(parent_id)
            if parent.children[child_index] != left_id:
                raise CorruptPage("BTree insertion path no longer matches parent")
            keys = list(parent.keys)
            children = list(parent.children)
            keys.insert(child_index, separator)
            children.insert(child_index + 1, right_id)
            updated = InternalPage(tuple(keys), tuple(children))
            try:
                body = encode_internal(updated)
            except PageFull:
                promoted, new_right_id = self._split_internal(parent_id, updated)
                left_id = parent_id
                separator = promoted
                right_id = new_right_id
            else:
                self._write_page(parent_id, PageKind.BTREE_INTERNAL, body)
                return

        new_root = InternalPage((separator,), (left_id, right_id))
        new_root_id = self._allocate_page(
            PageKind.BTREE_INTERNAL,
            encode_internal(new_root),
        )
        self._root_page_id = new_root_id
        self._height += 1
        self._write_meta()

    def _split_internal(
        self,
        page_id: int,
        page: InternalPage,
    ) -> tuple[bytes, int]:
        middle = len(page.keys) // 2
        promoted = page.keys[middle]
        left = InternalPage(
            page.keys[:middle],
            page.children[: middle + 1],
        )
        right = InternalPage(
            page.keys[middle + 1 :],
            page.children[middle + 1 :],
        )
        encode_internal(left)
        right_id = self._allocate_page(
            PageKind.BTREE_INTERNAL,
            encode_internal(right),
        )
        self._write_page(
            page_id,
            PageKind.BTREE_INTERNAL,
            encode_internal(left),
        )
        return promoted, right_id

    @staticmethod
    def _leaf_split_position(entries: tuple[LeafEntry, ...]) -> int:
        if len(entries) < 2:
            raise PageFull("one BTree leaf entry exceeds the page capacity")
        candidates: list[tuple[int, int]] = []
        for position in range(1, len(entries)):
            left_size = BTree._leaf_body_size(entries[:position])
            right_size = BTree._leaf_body_size(entries[position:])
            if left_size <= PAGE_BODY_SIZE and right_size <= PAGE_BODY_SIZE:
                candidates.append((abs(left_size - right_size), position))
        if not candidates:
            raise PageFull("BTree leaf cannot be split into valid pages")
        return min(candidates)[1]

    @staticmethod
    def _leaf_body_size(entries: tuple[LeafEntry, ...]) -> int:
        # Fixed leaf header plus key length, key bytes, and fixed TID.
        return 24 + sum(2 + len(entry.key) + 12 for entry in entries)

    def _read_internal(self, page_id: int) -> InternalPage:
        decoded = self._read_page(page_id, PageKind.BTREE_INTERNAL)
        return decode_internal(decoded)

    def _read_leaf(self, page_id: int) -> LeafPage:
        decoded = self._read_page(page_id, PageKind.BTREE_LEAF)
        return decode_leaf(decoded)

    def _read_page(self, page_id: int, expected_kind: PageKind) -> bytes:
        key = btree_page_key(self.index_id, page_id)
        with self._pool.fetch_page(key) as guard:
            decoded = decode_page(key, guard.page_bytes)
            if decoded.kind is not expected_kind:
                raise CorruptPage(
                    f"BTree page {page_id} has kind {decoded.kind.name}, "
                    f"expected {expected_kind.name}"
                )
            return decoded.body

    def _write_page(self, page_id: int, kind: PageKind, body: bytes) -> None:
        key = btree_page_key(self.index_id, page_id)
        with self._pool.fetch_page(key) as guard:
            self._replace_guard(guard, kind, body)

    def _allocate_page(self, kind: PageKind, body: bytes) -> int:
        with self._pool.new_page(self._relation, kind) as guard:
            self._replace_guard(guard, kind, body)
            return guard.key.page_id

    def _write_meta(self) -> None:
        self._write_page(
            0,
            PageKind.BTREE_META,
            encode_meta(MetaPage(self._root_page_id, self._height)),
        )

    @staticmethod
    def _replace_guard(guard: PageGuard, kind: PageKind, body: bytes) -> None:
        guard.replace_bytes(
            encode_page(
                guard.key,
                kind,
                page_lsn=0,
                body=body,
            )
        )
        guard.mark_dirty(page_lsn=0)
