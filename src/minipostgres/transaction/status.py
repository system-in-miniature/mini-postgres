"""In-process transaction status table, the teaching analogue of PG CLOG."""

from __future__ import annotations

import threading
from enum import Enum


class TransactionStatus(Enum):
    IN_PROGRESS = "in_progress"
    COMMITTED = "committed"
    ABORTED = "aborted"


class TransactionStatusTable:
    def __init__(
        self,
        statuses: dict[int, TransactionStatus] | None = None,
    ) -> None:
        self._statuses = dict(statuses or {})
        self._lock = threading.RLock()

    def get(self, xid: int) -> TransactionStatus:
        with self._lock:
            return self._statuses.get(xid, TransactionStatus.IN_PROGRESS)

    def set(self, xid: int, status: TransactionStatus) -> None:
        with self._lock:
            current = self.get(xid)
            if current is not TransactionStatus.IN_PROGRESS and current is not status:
                raise ValueError("transaction status is terminal")
            self._statuses[xid] = status

    def snapshot(self) -> tuple[tuple[int, TransactionStatus], ...]:
        with self._lock:
            return tuple(sorted(self._statuses.items()))
