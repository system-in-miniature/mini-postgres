"""Leaf-sibling range iteration with bounded pin ownership."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING

from minipostgres.index.pages import LeafPage
from minipostgres.row import TID
from minipostgres.storage.buffer import PageGuard

if TYPE_CHECKING:
    from minipostgres.index.btree import BTree


class BTreeRangeIterator:
    """Inclusive range iterator that pins only its current leaf."""

    def __init__(self, tree: BTree, lower: bytes, upper: bytes) -> None:
        self._tree = tree
        self._lower = lower
        self._upper = upper
        self._guard: PageGuard | None = None
        self._leaf: LeafPage | None = None
        self._position = 0
        self._closed = False
        self._load(tree.first_leaf_page(lower))

    @property
    def current_page_id(self) -> int | None:
        return None if self._guard is None else self._guard.key.page_id

    def __iter__(self) -> BTreeRangeIterator:
        return self

    def __next__(self) -> tuple[bytes, TID]:
        while not self._closed and self._leaf is not None:
            while self._position < len(self._leaf.entries):
                entry = self._leaf.entries[self._position]
                self._position += 1
                if entry.key < self._lower:
                    continue
                if entry.key > self._upper:
                    self.close()
                    raise StopIteration
                return entry.key, entry.tid
            next_page = self._leaf.right_sibling
            if next_page is None:
                self.close()
                raise StopIteration
            self._load(next_page)
        raise StopIteration

    def __enter__(self) -> BTreeRangeIterator:
        if self._closed:
            raise RuntimeError("range iterator is closed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the current leaf pin; repeated close is harmless."""

        if self._closed:
            return
        self._closed = True
        if self._guard is not None:
            self._guard.release()
        self._guard = None
        self._leaf = None

    def _load(self, page_id: int) -> None:
        if self._guard is not None:
            self._guard.release()
        self._guard, self._leaf = self._tree.pin_leaf(page_id)
        self._position = 0
