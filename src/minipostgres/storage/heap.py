"""Persistent heap-table access over slotted pages and tuple versions."""

from __future__ import annotations

import threading
from collections.abc import Iterator

from minipostgres.catalog.model import TableMetadata
from minipostgres.errors import CorruptPage, PageFull
from minipostgres.row import TID
from minipostgres.storage.buffer import BufferPool, PageGuard
from minipostgres.storage.constants import PAGE_BODY_SIZE, PageKind
from minipostgres.storage.free_space import FreeSpaceMap
from minipostgres.storage.identifiers import heap_page_key, heap_relation
from minipostgres.storage.page import decode_page, encode_page
from minipostgres.storage.slotted import SlottedPage
from minipostgres.storage.tuple import SYSTEM_XID, TupleCodec, TupleVersion
from minipostgres.types import Scalar


class HeapTable:
    """TableAccess implementation backed by stable physical heap TIDs."""

    def __init__(
        self,
        buffer_pool: BufferPool,
        metadata: TableMetadata,
        free_space: FreeSpaceMap,
    ) -> None:
        self._pool = buffer_pool
        self._metadata = metadata
        self.table_id = metadata.table_id
        self.schema = metadata.schema
        self.free_space = free_space
        self._relation = heap_relation(metadata.table_id)
        self._codec = TupleCodec(metadata.schema)
        self._lock = threading.RLock()

    @classmethod
    def open(
        cls,
        buffer_pool: BufferPool,
        metadata: TableMetadata,
    ) -> HeapTable:
        """Open a heap and repair missing free-space entries from actual pages."""

        free_space = FreeSpaceMap.open(
            buffer_pool.storage_root
            / "relations"
            / f"table-{metadata.table_id}.fsm",
            maximum_free_bytes=PAGE_BODY_SIZE,
        )
        heap = cls(buffer_pool, metadata, free_space)
        heap._bootstrap_free_space()
        return heap

    def insert(self, values: tuple[Scalar, ...]) -> TID:
        """Insert one physical tuple, repairing stale free-space estimates."""

        validated = self.schema.validate_row(values)
        encoded_tuple = self._codec.encode(
            TupleVersion(SYSTEM_XID, 0, None, validated)
        )
        # A dead slot can be reused without growing the directory. The FSM is
        # approximate, so use the tuple payload as the lower-bound candidate
        # size and let SlottedPage perform the exact fit check.
        required = len(encoded_tuple)
        with self._lock:
            for page_id in self.free_space.candidate_pages(required):
                tid = self._try_insert(page_id, encoded_tuple)
                if tid is not None:
                    return tid
            return self._insert_new_page(encoded_tuple)

    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None:
        """Fetch a live physical tuple by stable TID."""

        with self._lock:
            if tid.page_id >= self._pool.page_count(self._relation):
                return None
            with self._pool.fetch_page(
                heap_page_key(self.table_id, tid.page_id)
            ) as guard:
                page = self._slotted_page(guard)
                try:
                    encoded = page.read(tid.slot_id)
                except KeyError:
                    return None
                return self._codec.decode(encoded).values

    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
        """Return a page-order, slot-order snapshot of current live tuples."""

        with self._lock:
            rows: list[tuple[TID, tuple[Scalar, ...]]] = []
            for page_id in range(self._pool.page_count(self._relation)):
                key = heap_page_key(self.table_id, page_id)
                with self._pool.fetch_page(key) as guard:
                    page = self._slotted_page(guard)
                    rows.extend(
                        (
                            TID(page_id, slot_id),
                            self._codec.decode(page.read(slot_id)).values,
                        )
                        for slot_id in page.live_slots()
                    )
            return iter(rows)

    def replace(
        self,
        tid: TID,
        values: tuple[Scalar, ...],
    ) -> TID | None:
        """Insert a replacement tuple and retire the old physical slot."""

        validated = self.schema.validate_row(values)
        with self._lock:
            if self.fetch(tid) is None:
                return None
            replacement = self.insert(validated)
            if not self.delete(tid):
                raise RuntimeError("heap tuple disappeared during serialized replace")
            return replacement

    def delete(self, tid: TID) -> bool:
        """Mark one physical slot dead without renumbering other TIDs."""

        with self._lock:
            if tid.page_id >= self._pool.page_count(self._relation):
                return False
            key = heap_page_key(self.table_id, tid.page_id)
            with self._pool.fetch_page(key) as guard:
                page = self._slotted_page(guard)
                try:
                    page.delete(tid.slot_id)
                except KeyError:
                    return False
                self._publish_page(guard, page)
                self.free_space.record(tid.page_id, page.available_free_bytes)
                return True

    def _try_insert(self, page_id: int, encoded_tuple: bytes) -> TID | None:
        if page_id >= self._pool.page_count(self._relation):
            raise CorruptPage("free-space map refers to an unallocated heap page")
        key = heap_page_key(self.table_id, page_id)
        with self._pool.fetch_page(key) as guard:
            page = self._slotted_page(guard)
            try:
                slot_id = page.insert(encoded_tuple)
            except PageFull:
                self.free_space.record(page_id, page.available_free_bytes)
                return None
            self._publish_page(guard, page)
            self.free_space.record(page_id, page.available_free_bytes)
            return TID(page_id, slot_id)

    def _insert_new_page(self, encoded_tuple: bytes) -> TID:
        with self._pool.new_page(self._relation, PageKind.HEAP) as guard:
            page = SlottedPage.empty(guard.key.page_id)
            slot_id = page.insert(encoded_tuple)
            self._publish_page(guard, page)
            self.free_space.record(
                guard.key.page_id,
                page.available_free_bytes,
            )
            return TID(guard.key.page_id, slot_id)

    def _slotted_page(self, guard: PageGuard) -> SlottedPage:
        decoded = decode_page(guard.key, guard.page_bytes)
        if decoded.kind is not PageKind.HEAP:
            raise CorruptPage("heap relation contains a non-heap page")
        if not decoded.body:
            return SlottedPage.empty(guard.key.page_id)
        return SlottedPage.from_body(guard.key.page_id, decoded.body)

    @staticmethod
    def _publish_page(guard: PageGuard, page: SlottedPage) -> None:
        guard.replace_bytes(
            encode_page(
                guard.key,
                PageKind.HEAP,
                page_lsn=0,
                body=page.to_body(),
            )
        )
        guard.mark_dirty(page_lsn=0)

    def _bootstrap_free_space(self) -> None:
        page_count = self._pool.page_count(self._relation)
        if self.free_space.page_count > page_count:
            raise CorruptPage(
                "free-space map contains entries beyond the heap relation"
            )
        for page_id in range(self.free_space.page_count, page_count):
            key = heap_page_key(self.table_id, page_id)
            with self._pool.fetch_page(key) as guard:
                page = self._slotted_page(guard)
                self.free_space.record(page_id, page.available_free_bytes)
