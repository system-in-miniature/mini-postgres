"""Index-aware TableAccess wrapper for serialized Phase B statements."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from minipostgres.catalog.model import IndexMetadata, Schema
from minipostgres.errors import ConstraintViolation, TypeMismatch
from minipostgres.executor.memory import TableAccess
from minipostgres.index.btree import BTree
from minipostgres.index.key import KeyCodec
from minipostgres.row import TID
from minipostgres.storage.heap import HeapTable
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatusTable
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
        xid: int,
        snapshot: Snapshot,
        statuses: TransactionStatusTable,
        values: tuple[Scalar, ...],
    ) -> TID:
        heap = self._mvcc_heap()
        validated = self.schema.validate_row(values)
        keys = self._keys(validated)
        self._check_unique_visible(keys, heap, snapshot, xid, statuses)
        tid = heap.insert_version(xid, validated)
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
        xid: int,
        snapshot: Snapshot,
        statuses: TransactionStatusTable,
        values: tuple[Scalar, ...],
    ) -> TID | None:
        heap = self._mvcc_heap()
        old_values = heap.fetch_visible(tid, snapshot, xid, statuses)
        if old_values is None:
            return None
        validated = self.schema.validate_row(values)
        new_keys = self._keys(validated)
        self._check_unique_visible(
            new_keys,
            heap,
            snapshot,
            xid,
            statuses,
            ignored_tid=tid,
        )
        replacement = heap.replace_version(tid, xid, validated)
        if replacement is None:
            return None
        for binding, key in new_keys:
            binding.tree.insert(key, replacement)
        return replacement

    def delete_mvcc(self, tid: TID, xid: int) -> bool:
        return self._mvcc_heap().delete_version(tid, xid)

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
    def _check_unique_visible(
        keys: tuple[tuple[IndexBinding, bytes], ...],
        heap: HeapTable,
        snapshot: Snapshot,
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
                if heap.fetch_visible(candidate, snapshot, xid, statuses) is not None:
                    raise ConstraintViolation(
                        f"unique index {binding.metadata.name} rejects duplicate key"
                    )

    def _mvcc_heap(self) -> HeapTable:
        if not isinstance(self._heap, HeapTable):
            raise TypeError("MVCC requires a persistent heap")
        return self._heap
