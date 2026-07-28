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
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
from minipostgres.transaction.visibility import is_visible
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

    def insert_version(self, xid: int, values: tuple[Scalar, ...]) -> TID:
        validated = self.schema.validate_row(values)
        encoded = self._codec.encode(TupleVersion(xid, 0, None, validated))
        with self._lock:
            for page_id in self.free_space.candidate_pages(len(encoded)):
                if (tid := self._try_insert(page_id, encoded)) is not None:
                    return tid
            return self._insert_new_page(encoded)

    def fetch_visible(
        self,
        tid: TID,
        snapshot: Snapshot,
        current_xid: int,
        statuses: TransactionStatusTable,
    ) -> tuple[Scalar, ...] | None:
        resolved = self.resolve_visible(tid, snapshot, current_xid, statuses)
        return None if resolved is None else resolved[1]

    def resolve_visible(
        self,
        tid: TID,
        snapshot: Snapshot,
        current_xid: int,
        statuses: TransactionStatusTable,
    ) -> tuple[TID, tuple[Scalar, ...]] | None:
        """Resolve a version-chain root or member to its visible physical tuple."""

        with self._lock:
            current: TID | None = tid
            visited: set[TID] = set()
            visible: tuple[TID, TupleVersion] | None = None
            while current is not None:
                if current in visited:
                    raise CorruptPage("tuple version chain contains a cycle")
                visited.add(current)
                version = self.physical_version(current)
                if version is None:
                    break
                if is_visible(version, snapshot, current_xid, statuses):
                    visible = (current, version)
                current = version.next_tid
            if visible is None:
                return None
            visible_tid, visible_version = visible
            return visible_tid, visible_version.values

    def resolve_globally_live(
        self,
        tid: TID,
        current_xid: int,
        statuses: TransactionStatusTable,
    ) -> tuple[TID, tuple[Scalar, ...]] | None:
        """Resolve the newest committed-or-own version after a writer wait."""

        with self._lock:
            current: TID | None = self.root_tid(tid)
            live: tuple[TID, TupleVersion] | None = None
            visited: set[TID] = set()
            while current is not None:
                if current in visited:
                    raise CorruptPage("tuple version chain contains a cycle")
                visited.add(current)
                version = self.physical_version(current)
                if version is None:
                    break
                creator_committed = version.xmin in {SYSTEM_XID, current_xid} or (
                    statuses.get(version.xmin) is TransactionStatus.COMMITTED
                )
                deleter_committed = version.xmax == current_xid or (
                    version.xmax != 0
                    and statuses.get(version.xmax) is TransactionStatus.COMMITTED
                )
                if creator_committed and not deleter_committed:
                    live = (current, version)
                current = version.next_tid
            if live is None:
                return None
            live_tid, live_version = live
            return live_tid, live_version.values

    def scan_visible(
        self,
        snapshot: Snapshot,
        current_xid: int,
        statuses: TransactionStatusTable,
    ) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
        with self._lock:
            physical = tuple(self.scan_versions())
            continuations = {
                version.next_tid
                for _, version in physical
                if version.next_tid is not None
            }
            rows: list[tuple[TID, tuple[Scalar, ...]]] = []
            for tid, _ in physical:
                if tid in continuations:
                    continue
                resolved = self.resolve_visible(
                    tid,
                    snapshot,
                    current_xid,
                    statuses,
                )
                if resolved is not None:
                    rows.append(resolved)
            return iter(rows)

    def replace_version(
        self,
        tid: TID,
        xid: int,
        statuses: TransactionStatusTable,
        values: tuple[Scalar, ...],
    ) -> TID | None:
        with self._lock:
            old = self.physical_version(tid)
            if old is None or (
                old.xmax != 0
                and statuses.get(old.xmax) is not TransactionStatus.ABORTED
            ):
                return None
            replacement = self.insert_version(xid, values)
            self._set_version(
                tid,
                TupleVersion(old.xmin, xid, replacement, old.values),
            )
            return replacement

    def delete_version(
        self,
        tid: TID,
        xid: int,
        statuses: TransactionStatusTable,
    ) -> bool:
        with self._lock:
            old = self.physical_version(tid)
            if old is None or (
                old.xmax != 0
                and statuses.get(old.xmax) is not TransactionStatus.ABORTED
            ):
                return False
            self._set_version(
                tid,
                TupleVersion(old.xmin, xid, old.next_tid, old.values),
            )
            return True

    def physical_version(self, tid: TID) -> TupleVersion | None:
        if tid.page_id >= self._pool.page_count(self._relation):
            return None
        with self._pool.fetch_page(
            heap_page_key(self.table_id, tid.page_id)
        ) as guard:
            page = self._slotted_page(guard)
            try:
                return self._codec.decode(page.read(tid.slot_id))
            except KeyError:
                return None

    def scan_versions(self) -> Iterator[tuple[TID, TupleVersion]]:
        rows: list[tuple[TID, TupleVersion]] = []
        for page_id in range(self._pool.page_count(self._relation)):
            with self._pool.fetch_page(
                heap_page_key(self.table_id, page_id)
            ) as guard:
                page = self._slotted_page(guard)
                rows.extend(
                    (TID(page_id, slot_id), self._codec.decode(page.read(slot_id)))
                    for slot_id in page.live_slots()
                )
        return iter(rows)

    def root_tid(self, tid: TID) -> TID:
        """Return the oldest physical member of the chain containing ``tid``."""

        with self._lock:
            predecessors = {
                version.next_tid: candidate
                for candidate, version in self.scan_versions()
                if version.next_tid is not None
            }
            current = tid
            visited: set[TID] = set()
            while current in predecessors:
                if current in visited:
                    raise CorruptPage("tuple version chain contains a cycle")
                visited.add(current)
                current = predecessors[current]
            return current

    def _set_version(self, tid: TID, version: TupleVersion) -> None:
        key = heap_page_key(self.table_id, tid.page_id)
        with self._pool.fetch_page(key) as guard:
            page = self._slotted_page(guard)
            page.replace(tid.slot_id, self._codec.encode(version))
            self._publish_page(guard, page)
            self.free_space.record(tid.page_id, page.available_free_bytes)

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
