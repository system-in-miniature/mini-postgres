"""Index-aware TableAccess wrapper for serialized Phase B statements."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from minipostgres.catalog.model import IndexMetadata, Schema
from minipostgres.errors import ConstraintViolation, TypeMismatch
from minipostgres.executor.memory import TableAccess
from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.maintenance.horizon import (
    VersionDisposition,
    classify_version,
)
from minipostgres.maintenance.vacuum import VacuumResult
from minipostgres.row import TID
from minipostgres.storage.heap import HeapTable
from minipostgres.transaction.locks import (
    LockManager,
    TupleLockKey,
    UniqueKeyLockKey,
)
from minipostgres.transaction.model import Transaction
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
from minipostgres.types import Scalar


@dataclass(frozen=True, slots=True)
class IndexBinding:
    """One published index and the codec for its catalog columns."""

    metadata: IndexMetadata
    tree: BTree
    codec: KeyCodec

    def key(self, values: tuple[Scalar, ...]) -> bytes:
        try:
            return self.codec.encode(
                tuple(values[column_id] for column_id in self.metadata.column_ids)
            )
        except TypeMismatch as error:
            raise ConstraintViolation(str(error)) from error


class IndexedTableAccess:
    """Synchronously maintain all published indexes around heap changes."""

    def __init__(self, heap: TableAccess) -> None:
        self._heap = heap
        self.table_id = heap.table_id
        self.schema: Schema = heap.schema
        self._indexes: list[IndexBinding] = []

    @property
    def indexes(self) -> tuple[IndexBinding, ...]:
        return tuple(self._indexes)

    def add_index(self, binding: IndexBinding) -> None:
        if binding.metadata.table_id != self.table_id:
            raise ValueError("index belongs to a different table")
        if any(
            existing.metadata.index_id == binding.metadata.index_id
            for existing in self._indexes
        ):
            raise ValueError("index is already registered")
        self._indexes.append(binding)

    def rebuild_indexes(self, statuses: TransactionStatusTable) -> None:
        """Populate empty derived indexes from committed heap truth."""

        heap = self._mvcc_heap()
        for tid, values in heap.scan_globally_live(statuses):
            for binding, key in self._keys(values):
                binding.tree.insert(key, tid)

    def insert(self, values: tuple[Scalar, ...]) -> TID:
        validated = self.schema.validate_row(values)
        keys = self._keys(validated)
        self._check_unique(keys)
        tid = self._heap.insert(validated)
        inserted: list[tuple[IndexBinding, bytes]] = []
        try:
            for binding, key in keys:
                binding.tree.insert(key, tid)
                inserted.append((binding, key))
        except BaseException:
            for binding, key in reversed(inserted):
                binding.tree.delete(key, tid)
            self._heap.delete(tid)
            raise
        return tid

    def insert_mvcc(
        self,
        transaction: Transaction,
        statuses: TransactionStatusTable,
        locks: LockManager,
        values: tuple[Scalar, ...],
    ) -> TID:
        heap = self._mvcc_heap()
        validated = self.schema.validate_row(values)
        keys = self._keys(validated)
        self._acquire_unique_keys(transaction, locks, keys)
        self._check_unique_global(keys, heap, transaction.xid, statuses)
        tid = heap.insert_version(transaction, validated)
        for binding, key in keys:
            binding.tree.insert(key, tid)
        return tid

    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None:
        return self._heap.fetch(tid)

    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
        return self._heap.scan()

    def fetch_mvcc(
        self,
        tid: TID,
        snapshot: Snapshot,
        xid: int,
        statuses: TransactionStatusTable,
    ) -> tuple[Scalar, ...] | None:
        return self._mvcc_heap().fetch_visible(tid, snapshot, xid, statuses)

    def resolve_mvcc(
        self,
        tid: TID,
        snapshot: Snapshot,
        xid: int,
        statuses: TransactionStatusTable,
    ) -> tuple[TID, tuple[Scalar, ...]] | None:
        return self._mvcc_heap().resolve_visible(tid, snapshot, xid, statuses)

    def scan_mvcc(
        self,
        snapshot: Snapshot,
        xid: int,
        statuses: TransactionStatusTable,
    ) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
        return self._mvcc_heap().scan_visible(snapshot, xid, statuses)

    def replace(
        self,
        tid: TID,
        values: tuple[Scalar, ...],
    ) -> TID | None:
        old_values = self._heap.fetch(tid)
        if old_values is None:
            return None
        validated = self.schema.validate_row(values)
        old_keys = self._keys(old_values)
        new_keys = self._keys(validated)
        self._check_unique(new_keys, ignored_tid=tid)
        replacement = self._heap.replace(tid, validated)
        if replacement is None:
            return None
        for (binding, old_key), (_, new_key) in zip(
            old_keys,
            new_keys,
            strict=True,
        ):
            if not binding.tree.delete(old_key, tid):
                raise RuntimeError("published index is missing an updated heap TID")
            binding.tree.insert(new_key, replacement)
        return replacement

    def replace_mvcc(
        self,
        tid: TID,
        transaction: Transaction,
        snapshot: Snapshot,
        statuses: TransactionStatusTable,
        locks: LockManager,
        values: tuple[Scalar, ...],
    ) -> TID | None:
        heap = self._mvcc_heap()
        root_tid = heap.root_tid(tid)
        locks.acquire(transaction, TupleLockKey(self.table_id, root_tid))
        visible = heap.resolve_globally_live(
            root_tid,
            transaction.xid,
            statuses,
        )
        if visible is None:
            return None
        visible_tid, old_values = visible
        validated = self.schema.validate_row(values)
        old_keys = self._keys(old_values)
        new_keys = self._keys(validated)
        self._acquire_unique_keys(transaction, locks, new_keys)
        self._check_unique_global(
            new_keys,
            heap,
            transaction.xid,
            statuses,
            ignored_tid=visible_tid,
        )
        replacement = heap.replace_version(
            visible_tid,
            transaction,
            statuses,
            validated,
        )
        if replacement is None:
            return None
        hot = (
            replacement.page_id == visible_tid.page_id
            and tuple(key for _, key in old_keys)
            == tuple(key for _, key in new_keys)
        )
        if not hot:
            for binding, key in new_keys:
                binding.tree.insert(key, replacement)
        return replacement

    def delete_mvcc(
        self,
        tid: TID,
        transaction: Transaction,
        statuses: TransactionStatusTable,
        locks: LockManager,
    ) -> bool:
        heap = self._mvcc_heap()
        locks.acquire(
            transaction,
            TupleLockKey(self.table_id, heap.root_tid(tid)),
        )
        visible = heap.resolve_globally_live(tid, transaction.xid, statuses)
        deleted = (
            False
            if visible is None
            else heap.delete_version(
                visible[0],
                transaction,
                statuses,
            )
        )
        return deleted

    def delete(self, tid: TID) -> bool:
        values = self._heap.fetch(tid)
        if values is None:
            return False
        keys = self._keys(values)
        if not self._heap.delete(tid):
            return False
        for binding, key in keys:
            if not binding.tree.delete(key, tid):
                raise RuntimeError("published index is missing a deleted heap TID")
        return True

    def vacuum(
        self,
        transaction: Transaction,
        *,
        horizon: int,
        statuses: TransactionStatusTable,
    ) -> VacuumResult:
        heap = self._mvcc_heap()
        versions = tuple(heap.scan_versions())
        removed_versions = 0
        removed_indexes = 0
        reclaimed_bytes = 0
        hot_pruned = 0
        continuations = {
            version.next_tid
            for _, version in versions
            if version.next_tid is not None
        }
        processed: set[TID] = set()
        for root_tid, root_version in versions:
            if root_tid in continuations or root_version.next_tid is None:
                continue
            root_indexed = any(
                root_tid in binding.tree.search(binding.key(root_version.values))
                for binding in self._indexes
            )
            successor = heap.physical_version(root_version.next_tid)
            successor_indexed = successor is not None and any(
                root_version.next_tid
                in binding.tree.search(binding.key(successor.values))
                for binding in self._indexes
            )
            if not root_indexed or successor_indexed:
                continue
            chain = heap.version_chain(root_tid)
            processed.update(tid for tid, _ in chain)
            removable = {
                tid
                for tid, version in chain[1:]
                if classify_version(
                    version,
                    horizon=horizon,
                    statuses=statuses,
                )
                is VersionDisposition.DEAD
            }
            # Preserve the newest physical member unless the whole indexed
            # row can be removed by the ordinary path.
            if chain:
                removable.discard(chain[-1][0])
            pruned, reclaimed = heap.prune_chain(
                root_tid,
                removable,
                transaction,
            )
            hot_pruned += pruned
            removed_versions += pruned
            reclaimed_bytes += reclaimed
        for tid, version in versions:
            if tid in processed:
                continue
            # An indexed root must remain until chain pruning can retarget the
            # entry atomically. A normal update has independently indexed its
            # successor and is therefore safe to unlink.
            if version.next_tid is not None and self._indexes:
                successor = heap.physical_version(version.next_tid)
                if successor is None or any(
                    version.next_tid
                    not in binding.tree.search(binding.key(successor.values))
                    for binding in self._indexes
                ):
                    continue
            if (
                classify_version(
                    version,
                    horizon=horizon,
                    statuses=statuses,
                )
                is VersionDisposition.KEEP
            ):
                continue
            for binding, key in self._keys(version.values):
                if binding.tree.delete(key, tid):
                    removed_indexes += 1
            reclaimed = heap.reclaim_version(tid, transaction)
            if reclaimed:
                removed_versions += 1
                reclaimed_bytes += reclaimed
        return VacuumResult(
            heap.page_count,
            removed_versions,
            removed_indexes,
            reclaimed_bytes,
            hot_pruned,
        )

    def _keys(
        self,
        values: tuple[Scalar, ...],
    ) -> tuple[tuple[IndexBinding, bytes], ...]:
        return tuple((binding, binding.key(values)) for binding in self._indexes)

    @staticmethod
    def _check_unique(
        keys: tuple[tuple[IndexBinding, bytes], ...],
        *,
        ignored_tid: TID | None = None,
    ) -> None:
        for binding, key in keys:
            if not binding.metadata.unique:
                continue
            conflicts = tuple(
                candidate
                for candidate in binding.tree.search(key)
                if candidate != ignored_tid
            )
            if conflicts:
                raise ConstraintViolation(
                    f"unique index {binding.metadata.name} rejects duplicate key"
                )

    @staticmethod
    def _check_unique_global(
        keys: tuple[tuple[IndexBinding, bytes], ...],
        heap: HeapTable,
        xid: int,
        statuses: TransactionStatusTable,
        *,
        ignored_tid: TID | None = None,
    ) -> None:
        for binding, key in keys:
            if not binding.metadata.unique:
                continue
            for candidate in binding.tree.search(key):
                if candidate == ignored_tid:
                    continue
                version = heap.physical_version(candidate)
                if version is None:
                    continue
                creator = (
                    TransactionStatus.IN_PROGRESS
                    if version.xmin == xid
                    else statuses.get(version.xmin)
                )
                if creator is TransactionStatus.ABORTED:
                    continue
                if version.xmax == xid:
                    continue
                if (
                    version.xmax != 0
                    and statuses.get(version.xmax) is TransactionStatus.COMMITTED
                ):
                    continue
                raise ConstraintViolation(
                    f"unique index {binding.metadata.name} rejects duplicate key"
                )

    @staticmethod
    def _acquire_unique_keys(
        transaction: Transaction,
        locks: LockManager,
        keys: tuple[tuple[IndexBinding, bytes], ...],
    ) -> None:
        resources = sorted(
            (
                UniqueKeyLockKey(binding.metadata.index_id, key)
                for binding, key in keys
                if binding.metadata.unique
            ),
            key=lambda resource: (resource.index_id, resource.encoded_key),
        )
        for resource in resources:
            locks.acquire(transaction, resource)

    def _mvcc_heap(self) -> HeapTable:
        if not isinstance(self._heap, HeapTable):
            raise TypeError("MVCC requires a persistent heap")
        return self._heap
