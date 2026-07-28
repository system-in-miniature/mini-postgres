"""Retained in-memory reference implementation of the table access boundary."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from minipostgres.catalog.model import Schema
from minipostgres.row import TID
from minipostgres.types import Scalar


@runtime_checkable
class TableAccess(Protocol):
    """Storage-independent tuple operations required by relational execution."""

    table_id: int
    schema: Schema

    def insert(self, values: tuple[Scalar, ...]) -> TID: ...

    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None: ...

    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]: ...

    def replace(
        self,
        tid: TID,
        values: tuple[Scalar, ...],
    ) -> TID | None: ...

    def delete(self, tid: TID) -> bool: ...


class MemoryTable:
    """Append-only slots with tombstones and stable in-memory TIDs."""

    def __init__(self, table_id: int, schema: Schema) -> None:
        if table_id <= 0:
            raise ValueError("table ID must be positive")
        self.table_id = table_id
        self.schema = schema
        self._slots: list[tuple[Scalar, ...] | None] = []
        self._lock = threading.RLock()

    def insert(self, values: tuple[Scalar, ...]) -> TID:
        validated = self.schema.validate_row(values)
        with self._lock:
            tid = TID(0, len(self._slots))
            self._slots.append(validated)
            return tid

    def fetch(self, tid: TID) -> tuple[Scalar, ...] | None:
        with self._lock:
            index = self._slot_index(tid)
            if index is None:
                return None
            return self._slots[index]

    def scan(self) -> Iterator[tuple[TID, tuple[Scalar, ...]]]:
        with self._lock:
            snapshot = tuple(self._slots)
        return (
            (TID(0, slot_id), values)
            for slot_id, values in enumerate(snapshot)
            if values is not None
        )

    def replace(
        self,
        tid: TID,
        values: tuple[Scalar, ...],
    ) -> TID | None:
        validated = self.schema.validate_row(values)
        with self._lock:
            index = self._slot_index(tid)
            if index is None or self._slots[index] is None:
                return None
            self._slots[index] = validated
            return tid

    def delete(self, tid: TID) -> bool:
        with self._lock:
            index = self._slot_index(tid)
            if index is None or self._slots[index] is None:
                return False
            self._slots[index] = None
            return True

    def _slot_index(self, tid: TID) -> int | None:
        if tid.page_id != 0 or tid.slot_id >= len(self._slots):
            return None
        return tid.slot_id
