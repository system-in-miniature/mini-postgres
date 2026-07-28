from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum

from minipostgres.errors import TransactionAborted


class IsolationLevel(Enum):
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"


class TransactionState(Enum):
    ACTIVE = "active"
    FAILED = "failed"
    COMMITTED = "committed"
    ABORTED = "aborted"


@dataclass(slots=True)
class Transaction:
    xid: int
    isolation: IsolationLevel
    state: TransactionState = TransactionState.ACTIVE
    repeatable_snapshot: object | None = None
    has_writes: bool = False
    resources: set[object] = field(default_factory=lambda: set[object]())
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def require_usable(self) -> None:
        if self.state is not TransactionState.ACTIVE:
            raise TransactionAborted(f"transaction {self.xid} is {self.state.value}")

    def mark_failed(self) -> None:
        with self._lock:
            self.require_usable()
            self.state = TransactionState.FAILED

    def mark_committed(self) -> None:
        with self._lock:
            if self.state is not TransactionState.ACTIVE:
                raise TransactionAborted("only an active transaction can commit")
            self.state = TransactionState.COMMITTED

    def mark_aborted(self) -> None:
        with self._lock:
            if self.state is TransactionState.COMMITTED:
                raise TransactionAborted("committed transaction cannot abort")
            self.state = TransactionState.ABORTED
