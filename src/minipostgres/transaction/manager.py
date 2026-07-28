from __future__ import annotations

import threading

from minipostgres.testing.failpoints import hit
from minipostgres.transaction.locks import LockManager
from minipostgres.transaction.model import (
    IsolationLevel,
    Transaction,
    TransactionState,
)
from minipostgres.transaction.snapshot import Snapshot
from minipostgres.transaction.status import TransactionStatus, TransactionStatusTable
from minipostgres.wal.manager import WalManager
from minipostgres.wal.records import AbortRecord, CommitRecord


class TransactionManager:
    def __init__(
        self,
        *,
        next_xid: int = 2,
        statuses: TransactionStatusTable | None = None,
        wal: WalManager | None = None,
    ) -> None:
        self._next_xid = next_xid
        self._active: dict[int, Transaction] = {}
        self.statuses = statuses or TransactionStatusTable()
        self.locks = LockManager(
            deadlock_victim_handler=self._abort_deadlock_victim
        )
        self._wal = wal
        self._lock = threading.RLock()

    @property
    def next_xid(self) -> int:
        with self._lock:
            return self._next_xid

    def begin(
        self,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    ) -> Transaction:
        with self._lock:
            transaction = Transaction(self._next_xid, isolation)
            self._next_xid += 1
            self._active[transaction.xid] = transaction
            return transaction

    def statement_snapshot(self, transaction: Transaction) -> Snapshot:
        with self._lock:
            transaction.require_usable()
            if (
                transaction.isolation is IsolationLevel.REPEATABLE_READ
                and transaction.repeatable_snapshot is not None
            ):
                return transaction.repeatable_snapshot
            snapshot = Snapshot(
                self._next_xid,
                frozenset(
                    xid for xid in self._active if xid != transaction.xid
                ),
            )
            if transaction.isolation is IsolationLevel.REPEATABLE_READ:
                transaction.repeatable_snapshot = snapshot
            return snapshot

    def commit(self, transaction: Transaction) -> None:
        with self._lock:
            if transaction.has_writes and self._wal is not None:
                self._wal.append(transaction.xid, CommitRecord())
                hit("after_commit_append_before_flush")
                self._wal.flush(self._wal.end_lsn)
                hit("after_commit_flush_before_response")
            transaction.mark_committed()
            self.statuses.set(transaction.xid, TransactionStatus.COMMITTED)
            self._active.pop(transaction.xid, None)
            self.locks.release_all(transaction)

    def abort(self, transaction: Transaction) -> None:
        with self._lock:
            if (
                transaction.has_writes
                and transaction.state is not TransactionState.ABORTED
                and self._wal is not None
            ):
                self._wal.append(transaction.xid, AbortRecord())
                self._wal.flush(self._wal.end_lsn)
            if transaction.state is not TransactionState.ABORTED:
                transaction.mark_aborted()
            self.statuses.set(transaction.xid, TransactionStatus.ABORTED)
            self._active.pop(transaction.xid, None)
            self.locks.release_all(transaction)

    def active_transactions(self) -> tuple[Transaction, ...]:
        with self._lock:
            return tuple(self._active.values())

    def _abort_deadlock_victim(self, transaction: Transaction) -> None:
        transaction.mark_failed()
        self.abort(transaction)
