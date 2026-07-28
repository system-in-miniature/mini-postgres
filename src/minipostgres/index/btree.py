"""Persistent page-based B+Tree insertion and point search."""

from __future__ import annotations

import threading
from bisect import bisect_left, bisect_right
from typing import TYPE_CHECKING, cast

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

if TYPE_CHECKING:
    from minipostgres.index.iterator import BTreeRangeIterator


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

    @property
    def relation(self):
        """Return the physical relation identity used by this tree."""

        return self._relation

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

    def delete(self, key: bytes, tid: TID) -> bool:
        """Delete one exact key/TID pair and rebalance reachable pages."""

        with self._lock:
            leaf_id = self._locate_entry_leaf(key, tid)
            if leaf_id is None:
                return False
            path = self._path_to_page(leaf_id)
            if path is None:
                raise CorruptPage("reachable BTree leaf has no root path")
            leaf = self._read_leaf(leaf_id)
            entries = list(leaf.entries)
            target = LeafEntry(key, tid)
            try:
                entries.remove(target)
            except ValueError:
                return False
            updated = LeafPage(
                tuple(entries),
                leaf.left_sibling,
                leaf.right_sibling,
            )
            self._write_page(leaf_id, PageKind.BTREE_LEAF, encode_leaf(updated))
            self._rebalance_leaf(leaf_id, updated, path)
            self._refresh_all_separators(self._root_page_id, self._height)
            return True

    def range(self, lower: bytes, upper: bytes) -> BTreeRangeIterator:
        """Create an inclusive sibling-backed range iterator."""

        if lower > upper:
            raise ValueError("range lower bound must not exceed upper bound")
        from minipostgres.index.iterator import BTreeRangeIterator

        return BTreeRangeIterator(self, lower, upper)

    def first_leaf_page(self, key: bytes) -> int:
        """Return the leftmost leaf that may contain the requested key."""

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
            return leaf_id

    def pin_leaf(self, page_id: int) -> tuple[PageGuard, LeafPage]:
        """Pin and decode one leaf for a range iterator."""

        key = btree_page_key(self.index_id, page_id)
        guard = self._pool.fetch_page(key)
        try:
            decoded = decode_page(key, guard.page_bytes)
            if decoded.kind is not PageKind.BTREE_LEAF:
                raise CorruptPage(f"BTree page {page_id} is not a leaf")
            return guard, decode_leaf(decoded.body)
        except BaseException:
            guard.release()
            raise

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

    def _locate_entry_leaf(self, key: bytes, tid: TID) -> int | None:
        leaf_id = self.first_leaf_page(key)
        while True:
            leaf = self._read_leaf(leaf_id)
            if LeafEntry(key, tid) in leaf.entries:
                return leaf_id
            if (
                leaf.right_sibling is None
                or (leaf.entries and leaf.entries[-1].key > key)
            ):
                return None
            right = self._read_leaf(leaf.right_sibling)
            if right.entries and right.entries[0].key > key:
                return None
            leaf_id = leaf.right_sibling

    def _path_to_page(self, target_page_id: int) -> list[tuple[int, int]] | None:
        def visit(
            page_id: int,
            height: int,
            path: list[tuple[int, int]],
        ) -> list[tuple[int, int]] | None:
            if height == 1:
                return path if page_id == target_page_id else None
            internal = self._read_internal(page_id)
            for child_index, child_id in enumerate(internal.children):
                found = visit(
                    child_id,
                    height - 1,
                    [*path, (page_id, child_index)],
                )
                if found is not None:
                    return found
            return None

        return visit(self._root_page_id, self._height, [])

    def _rebalance_leaf(
        self,
        page_id: int,
        page: LeafPage,
        path: list[tuple[int, int]],
    ) -> None:
        if not path:
            return
        if len(encode_leaf(page)) >= PAGE_BODY_SIZE // 2 and page.entries:
            return
        parent_id, child_index = path[-1]
        ancestors = path[:-1]
        parent = self._read_internal(parent_id)

        if child_index > 0:
            left_id = parent.children[child_index - 1]
            left = self._read_leaf(left_id)
            if left.entries:
                borrowed = left.entries[-1]
                new_left = LeafPage(
                    left.entries[:-1],
                    left.left_sibling,
                    left.right_sibling,
                )
                new_page = LeafPage(
                    (borrowed, *page.entries),
                    page.left_sibling,
                    page.right_sibling,
                )
                if self._leaf_can_lend(new_left) and self._leaf_fits(new_page):
                    keys = list(parent.keys)
                    keys[child_index - 1] = new_page.entries[0].key
                    self._write_page(
                        left_id, PageKind.BTREE_LEAF, encode_leaf(new_left)
                    )
                    self._write_page(
                        page_id, PageKind.BTREE_LEAF, encode_leaf(new_page)
                    )
                    self._write_page(
                        parent_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(
                            InternalPage(tuple(keys), parent.children)
                        ),
                    )
                    return

        if child_index + 1 < len(parent.children):
            right_id = parent.children[child_index + 1]
            right = self._read_leaf(right_id)
            if right.entries:
                borrowed = right.entries[0]
                new_page = LeafPage(
                    (*page.entries, borrowed),
                    page.left_sibling,
                    page.right_sibling,
                )
                new_right = LeafPage(
                    right.entries[1:],
                    right.left_sibling,
                    right.right_sibling,
                )
                if self._leaf_can_lend(new_right) and self._leaf_fits(new_page):
                    keys = list(parent.keys)
                    keys[child_index] = new_right.entries[0].key
                    self._write_page(
                        page_id, PageKind.BTREE_LEAF, encode_leaf(new_page)
                    )
                    self._write_page(
                        right_id, PageKind.BTREE_LEAF, encode_leaf(new_right)
                    )
                    self._write_page(
                        parent_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(
                            InternalPage(tuple(keys), parent.children)
                        ),
                    )
                    return

        if child_index > 0:
            left_id = parent.children[child_index - 1]
            left = self._read_leaf(left_id)
            merged = LeafPage(
                (*left.entries, *page.entries),
                left.left_sibling,
                page.right_sibling,
            )
            if self._leaf_fits(merged):
                self._write_page(
                    left_id, PageKind.BTREE_LEAF, encode_leaf(merged)
                )
                if page.right_sibling is not None:
                    self._set_leaf_left_sibling(page.right_sibling, left_id)
                reduced = self._remove_parent_child(parent, child_index)
                self._write_page(
                    parent_id,
                    PageKind.BTREE_INTERNAL,
                    encode_internal(reduced),
                )
                self._rebalance_internal(parent_id, reduced, ancestors)
                return

        if child_index + 1 < len(parent.children):
            right_id = parent.children[child_index + 1]
            right = self._read_leaf(right_id)
            merged = LeafPage(
                (*page.entries, *right.entries),
                page.left_sibling,
                right.right_sibling,
            )
            if self._leaf_fits(merged):
                self._write_page(
                    page_id, PageKind.BTREE_LEAF, encode_leaf(merged)
                )
                if right.right_sibling is not None:
                    self._set_leaf_left_sibling(right.right_sibling, page_id)
                reduced = self._remove_parent_child(parent, child_index + 1)
                self._write_page(
                    parent_id,
                    PageKind.BTREE_INTERNAL,
                    encode_internal(reduced),
                )
                self._rebalance_internal(parent_id, reduced, ancestors)

    def _rebalance_internal(
        self,
        page_id: int,
        page: InternalPage,
        ancestors: list[tuple[int, int]],
    ) -> None:
        if page_id == self._root_page_id:
            if len(page.children) == 1 and self._height > 1:
                self._root_page_id = page.children[0]
                self._height -= 1
                self._write_meta()
            return
        if len(encode_internal(page)) >= PAGE_BODY_SIZE // 2:
            return
        if not ancestors:
            raise CorruptPage("non-root internal page has no parent path")
        parent_id, child_index = ancestors[-1]
        higher = ancestors[:-1]
        parent = self._read_internal(parent_id)

        if child_index > 0:
            left_id = parent.children[child_index - 1]
            left = self._read_internal(left_id)
            if left.keys:
                new_left = InternalPage(left.keys[:-1], left.children[:-1])
                new_page = InternalPage(
                    (parent.keys[child_index - 1], *page.keys),
                    (left.children[-1], *page.children),
                )
                if self._internal_can_lend(new_left) and self._internal_fits(
                    new_page
                ):
                    keys = list(parent.keys)
                    keys[child_index - 1] = left.keys[-1]
                    self._write_page(
                        left_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(new_left),
                    )
                    self._write_page(
                        page_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(new_page),
                    )
                    self._write_page(
                        parent_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(
                            InternalPage(tuple(keys), parent.children)
                        ),
                    )
                    return

        if child_index + 1 < len(parent.children):
            right_id = parent.children[child_index + 1]
            right = self._read_internal(right_id)
            if right.keys:
                new_page = InternalPage(
                    (*page.keys, parent.keys[child_index]),
                    (*page.children, right.children[0]),
                )
                new_right = InternalPage(right.keys[1:], right.children[1:])
                if self._internal_can_lend(new_right) and self._internal_fits(
                    new_page
                ):
                    keys = list(parent.keys)
                    keys[child_index] = right.keys[0]
                    self._write_page(
                        page_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(new_page),
                    )
                    self._write_page(
                        right_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(new_right),
                    )
                    self._write_page(
                        parent_id,
                        PageKind.BTREE_INTERNAL,
                        encode_internal(
                            InternalPage(tuple(keys), parent.children)
                        ),
                    )
                    return

        if child_index > 0:
            left_id = parent.children[child_index - 1]
            left = self._read_internal(left_id)
            merged = InternalPage(
                (*left.keys, parent.keys[child_index - 1], *page.keys),
                (*left.children, *page.children),
            )
            if self._internal_fits(merged):
                self._write_page(
                    left_id,
                    PageKind.BTREE_INTERNAL,
                    encode_internal(merged),
                )
                reduced = self._remove_parent_child(parent, child_index)
                self._write_page(
                    parent_id,
                    PageKind.BTREE_INTERNAL,
                    encode_internal(reduced),
                )
                self._rebalance_internal(parent_id, reduced, higher)
                return

        if child_index + 1 < len(parent.children):
            right_id = parent.children[child_index + 1]
            right = self._read_internal(right_id)
            merged = InternalPage(
                (*page.keys, parent.keys[child_index], *right.keys),
                (*page.children, *right.children),
            )
            if self._internal_fits(merged):
                self._write_page(
                    page_id,
                    PageKind.BTREE_INTERNAL,
                    encode_internal(merged),
                )
                reduced = self._remove_parent_child(parent, child_index + 1)
                self._write_page(
                    parent_id,
                    PageKind.BTREE_INTERNAL,
                    encode_internal(reduced),
                )
                self._rebalance_internal(parent_id, reduced, higher)

    @staticmethod
    def _remove_parent_child(
        parent: InternalPage,
        child_index: int,
    ) -> InternalPage:
        children = list(parent.children)
        keys = list(parent.keys)
        children.pop(child_index)
        keys.pop(child_index - 1 if child_index > 0 else 0)
        return InternalPage(tuple(keys), tuple(children))

    def _set_leaf_left_sibling(self, page_id: int, left_id: int) -> None:
        leaf = self._read_leaf(page_id)
        self._write_page(
            page_id,
            PageKind.BTREE_LEAF,
            encode_leaf(
                LeafPage(leaf.entries, left_id, leaf.right_sibling)
            ),
        )

    @staticmethod
    def _leaf_fits(page: LeafPage) -> bool:
        try:
            encode_leaf(page)
        except PageFull:
            return False
        return True

    @staticmethod
    def _leaf_can_lend(page: LeafPage) -> bool:
        return bool(page.entries) and len(encode_leaf(page)) >= PAGE_BODY_SIZE // 2

    @staticmethod
    def _internal_fits(page: InternalPage) -> bool:
        try:
            encode_internal(page)
        except PageFull:
            return False
        return True

    @staticmethod
    def _internal_can_lend(page: InternalPage) -> bool:
        return bool(page.keys) and len(encode_internal(page)) >= PAGE_BODY_SIZE // 2

    def _refresh_all_separators(
        self,
        page_id: int,
        height: int,
    ) -> bytes | None:
        if height == 1:
            leaf = self._read_leaf(page_id)
            if not leaf.entries:
                return None
            return leaf.entries[0].key
        internal = self._read_internal(page_id)
        first_keys = [
            self._refresh_all_separators(child, height - 1)
            for child in internal.children
        ]
        if any(key is None for key in first_keys[1:]):
            raise CorruptPage("non-leftmost BTree subtree is empty")
        refreshed = InternalPage(
            tuple(cast(bytes, key) for key in first_keys[1:]),
            internal.children,
        )
        if refreshed != internal:
            self._write_page(
                page_id,
                PageKind.BTREE_INTERNAL,
                encode_internal(refreshed),
            )
        return first_keys[0]

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
